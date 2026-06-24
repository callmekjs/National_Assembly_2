# service/llm/llm_client.py
"""Generate 노드에서 쓰는 통합 chat().

OPENAI_API_KEY가 있으면 OpenAI Chat Completions를 우선 사용하고,
없거나 실패 시 로컬 HF(LoRA)로 폴백한다."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, Generator

import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env", override=True)
load_dotenv()

HF_REPO_ID = os.getenv("MODEL_DIR_ADAPTER", "./models/adapters/llama3.2-3b-ko-report-lora")
HF_BASE_MODEL = os.getenv("MODEL_DIR_BASE", "./models/base/Llama-3.2-3B")
HF_TRUST = os.getenv("HF_TRUST_REMOTE_CODE", "false").lower() == "true"
HF_TOKEN = os.getenv("HUGGINGFACE_HUB_TOKEN")

IS_RUNPOD = os.getenv("IS_RUNPOD", "false").lower() == "true"

if IS_RUNPOD:
    HF_DEVICE_MAP = os.getenv("HF_DEVICE_MAP", "cuda")
    HF_DTYPE = os.getenv("HF_DTYPE", "bfloat16")
    HF_4BIT = os.getenv("HF_4BIT", "false").lower() == "true"
else:
    HF_DEVICE_MAP = os.getenv("HF_DEVICE_MAP", "cpu")
    HF_DTYPE = os.getenv("HF_DTYPE", "float32")
    HF_4BIT = os.getenv("HF_4BIT", "false").lower() == "true"

_tokenizer = None
_model = None

# ── 인메모리 응답 캐시 ──────────────────────────────────────────────
_CACHE: dict[str, str] = {}


def _cache_key(system: str, user: str, history: list[dict] | None = None) -> str:
    history_str = json.dumps(history or [], ensure_ascii=False, sort_keys=True)
    raw = f"{system}\x00{history_str}\x00{user}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_clear() -> int:
    """캐시 비우기. 반환값: 삭제된 항목 수."""
    n = len(_CACHE)
    _CACHE.clear()
    return n


def _openai_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or "").strip()


def _use_openai() -> bool:
    if (os.getenv("FORCE_LOCAL_LLM") or "").lower() in ("1", "true", "yes"):
        return False
    return bool(_openai_key())


def _torch_dtype():
    import torch
    if HF_DEVICE_MAP == "cpu":
        return torch.float32
    return {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }.get(HF_DTYPE, torch.bfloat16)


def _hf_auth_kwargs() -> Dict[str, str]:
    return {"token": HF_TOKEN} if HF_TOKEN else {}


def _load_tokenizer(path_or_id: str):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(
        path_or_id,
        use_fast=True,
        trust_remote_code=HF_TRUST,
        **_hf_auth_kwargs(),
    )


def _load_model_lora(base_path: str, lora_path: str):
    from transformers import AutoModelForCausalLM
    from peft import PeftModel
    if HF_4BIT:
        from transformers import BitsAndBytesConfig

        base_model = AutoModelForCausalLM.from_pretrained(
            base_path,
            trust_remote_code=HF_TRUST,
            quantization_config=BitsAndBytesConfig(load_in_4bit=True),
            device_map="auto",
            **_hf_auth_kwargs(),
        )
    else:
        base_model = AutoModelForCausalLM.from_pretrained(
            base_path,
            trust_remote_code=HF_TRUST,
            device_map=HF_DEVICE_MAP,
            torch_dtype=_torch_dtype(),
            **_hf_auth_kwargs(),
        )
    model = PeftModel.from_pretrained(
        base_model,
        lora_path,
        **_hf_auth_kwargs(),
    )
    model.eval()
    return model


def _load():
    global _tokenizer, _model
    if _tokenizer is not None and _model is not None:
        return _tokenizer, _model

    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"

    _tokenizer = _load_tokenizer(HF_BASE_MODEL)
    _model = _load_model_lora(HF_BASE_MODEL, HF_REPO_ID)

    if _tokenizer.pad_token_id is None and _tokenizer.eos_token_id is not None:
        _tokenizer.pad_token = _tokenizer.eos_token

    if getattr(_model.config, "pad_token_id", None) is None:
        _model.config.pad_token_id = _tokenizer.pad_token_id
    if getattr(_model.config, "bos_token_id", None) is None and _tokenizer.bos_token_id is not None:
        _model.config.bos_token_id = _tokenizer.bos_token_id
    if getattr(_model.config, "eos_token_id", None) is None and _tokenizer.eos_token_id is not None:
        _model.config.eos_token_id = _tokenizer.eos_token_id

    return _tokenizer, _model


def _apply_chat_template_safe(tokenizer, messages):
    try:
        return tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        )
    except Exception:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in messages if m["role"] == "user"), "")
        prompt = f"""[INST] <<SYS>>
{system.strip()}
<</SYS>>

{user.strip()} [/INST]
"""
        return tokenizer(prompt, return_tensors="pt").input_ids


def _stream_openai(
    system: str, user: str, max_tokens: int,
    history: list[dict] | None = None,
) -> Generator[str, None, None]:
    api_key = _openai_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 없음")

    base = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    messages = [{"role": "system", "content": system.strip()}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user.strip()})
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0")),
        "seed": int(os.getenv("OPENAI_SEED", "42")),
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    with requests.post(
        url, headers=headers, data=json.dumps(payload, ensure_ascii=False),
        timeout=120, stream=True
    ) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data.strip() == "[DONE]":
                break
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


def chat_stream(
    system: str, user: str, max_tokens: int = 512,
    history: list[dict] | None = None,
) -> Generator[str, None, None]:
    """OpenAI SSE 스트리밍. 캐시 hit 시 즉시 반환. 로컬 HF는 비스트리밍 폴백."""
    key = _cache_key(system, user, history)
    if key in _CACHE:
        print("[LLM] stream cache hit", file=sys.stderr)
        yield _CACHE[key]
        return

    if _use_openai():
        try:
            print("[LLM] stream=True backend=openai model=", os.getenv("OPENAI_MODEL", "gpt-4o-mini"), file=sys.stderr)
            accumulated: list[str] = []
            for chunk in _stream_openai(system, user, max_tokens, history=history):
                accumulated.append(chunk)
                yield chunk
            full = "".join(accumulated)
            if full and not is_chat_failure_message(full):
                _CACHE[key] = full
            return
        except Exception as exc:
            print(f"[LLM] OpenAI stream 실패: {exc}", file=sys.stderr)
            if (os.getenv("OPENAI_ONLY") or "").lower() in ("1", "true", "yes"):
                yield "OpenAI API 호출에 실패했습니다. 키·네트워크·`OPENAI_BASE_URL`을 확인하거나 잠시 후 다시 시도해 주세요."
                return
    try:
        print("[LLM] stream=fallback backend=local_hf", file=sys.stderr)
        result = _chat_local_hf(system, user, max_tokens, history=history)
        if result and not is_chat_failure_message(result):
            _CACHE[key] = result
        yield result
    except Exception as exc:
        yield (
            "죄송합니다. 로컬 LLM 답변 생성에 실패했습니다. "
            f"({exc}) `.env`에 `OPENAI_API_KEY`를 설정하면 OpenAI로 생성할 수 있습니다."
        )


def _chat_openai(
    system: str, user: str, max_tokens: int,
    history: list[dict] | None = None,
) -> str:
    api_key = _openai_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 없음")

    base = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    messages = [{"role": "system", "content": system.strip()}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user.strip()})
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0")),
        "seed": int(os.getenv("OPENAI_SEED", "42")),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, data=json.dumps(payload, ensure_ascii=False), timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return str(data["choices"][0]["message"]["content"]).strip()


def _chat_local_hf(
    system: str, user: str, max_tokens: int,
    history: list[dict] | None = None,
) -> str:
    print("[LLM] HF_REPO_ID =", HF_REPO_ID, file=sys.stderr)
    print("[LLM] HF_BASE_MODEL =", HF_BASE_MODEL, file=sys.stderr)
    print("[LLM] CWD =", os.getcwd(), file=sys.stderr)

    tokenizer, model = _load()

    messages = [{"role": "system", "content": system.strip()}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user.strip()})
    input_ids = _apply_chat_template_safe(tokenizer, messages).to(model.device)
    attention_mask = (input_ids != tokenizer.pad_token_id).long()
    attention_mask = attention_mask.to(model.device)

    gen_out = model.generate(
        input_ids=input_ids,
        attention_mask=attention_mask,
        max_new_tokens=max_tokens,
        do_sample=False,
        pad_token_id=tokenizer.eos_token_id,
        eos_token_id=tokenizer.eos_token_id,
        use_cache=os.environ.get("IS_RUNPOD", "False").lower() == "true",
    )
    output_ids = gen_out[0][input_ids.shape[-1]:]
    return tokenizer.decode(output_ids, skip_special_tokens=True).strip()


def is_chat_failure_message(text: str) -> bool:
    """chat()이 모델 미기동·API 실패 시 돌려주는 안내 문구인지(예외 없이 문자열로 반환된 경우)."""
    if not text or not text.strip():
        return False
    markers = (
        "로컬 LLM 답변 생성에 실패",
        "OpenAI API 호출에 실패",
    )
    return any(m in text for m in markers)


def llm_env_probe() -> tuple[bool, str]:
    """
    무거운 모델 로드 없이 키·로컬 경로만 검사.
    Returns:
        (True, "") — 설정상으로는 생성 시도 가능
        (False, msg) — 홈/질의 화면에 띄울 짧은 안내
    """
    if _use_openai():
        return True, ""
    base = Path(HF_BASE_MODEL).expanduser()
    lora = Path(HF_REPO_ID).expanduser()
    missing: list[str] = []
    if not base.exists():
        missing.append(f"베이스 `{HF_BASE_MODEL}`")
    if not lora.exists():
        missing.append(f"LoRA `{HF_REPO_ID}`")
    if missing:
        return False, (
            "로컬 LLM 경로가 없고 `OPENAI_API_KEY`도 없습니다. "
            + ", ".join(missing)
            + " 를 확인하거나 `.env`에 OpenAI 키를 설정하세요."
        )
    return True, ""


def chat(
    system: str, user: str, max_tokens: int = 512,
    history: list[dict] | None = None,
) -> str:
    """캐시 hit 시 즉시 반환. miss 시 OpenAI → 로컬 HF 순으로 시도."""
    key = _cache_key(system, user, history)
    if key in _CACHE:
        print("[LLM] cache hit", file=sys.stderr)
        return _CACHE[key]

    result: str
    if _use_openai():
        try:
            print("[LLM] backend=openai model=", os.getenv("OPENAI_MODEL", "gpt-4o-mini"), file=sys.stderr)
            result = _chat_openai(system, user, max_tokens, history=history)
        except Exception as exc:
            print(f"[LLM] OpenAI 실패: {exc}", file=sys.stderr)
            if (os.getenv("OPENAI_ONLY") or "").lower() in ("1", "true", "yes"):
                return (
                    "OpenAI API 호출에 실패했습니다. 키·네트워크·`OPENAI_BASE_URL`을 확인하거나 "
                    "잠시 후 다시 시도해 주세요."
                )
            try:
                print("[LLM] backend=local_hf (fallback)", file=sys.stderr)
                result = _chat_local_hf(system, user, max_tokens, history=history)
            except Exception as exc2:
                return (
                    "죄송합니다. 로컬 LLM 답변 생성에 실패했습니다. "
                    f"({exc2}) `.env`에 `OPENAI_API_KEY`를 설정하면 OpenAI로 생성할 수 있습니다."
                )
    else:
        try:
            print("[LLM] backend=local_hf", file=sys.stderr)
            result = _chat_local_hf(system, user, max_tokens, history=history)
        except Exception as exc:
            return (
                "죄송합니다. 로컬 LLM 답변 생성에 실패했습니다. "
                f"({exc}) `.env`에 `OPENAI_API_KEY`를 설정하면 OpenAI로 생성할 수 있습니다."
            )

    if result and not is_chat_failure_message(result):
        _CACHE[key] = result
    return result
