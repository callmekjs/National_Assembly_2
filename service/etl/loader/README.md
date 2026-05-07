# ETL Loader

`service/etl/loader`는 변환 완료된 JSONL 데이터를 저장소에 적재하는 단계입니다.

## 실행

```bash
python -m service.etl.loader.loader_cli db create
python -m service.etl.loader.loader_cli load doc --jsonl-dir data/transform/final
python -m service.etl.loader.loader_cli load vector
```

## 구성

- `schema_jsonl.sql`: 적재용 테이블 생성 스크립트
- `jsonl_to_postgres.py`: JSONL 문서 적재
- `embeddings.py`: 임베딩 생성 및 저장
- `loader_cli.py`: 실행 엔트리포인트
