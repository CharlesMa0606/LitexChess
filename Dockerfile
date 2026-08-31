FROM rust:1.85-bookworm AS litex-builder
ARG LITEX_REPO=https://github.com/litexlang/golitex.git
ARG LITEX_REF=e049fabc6d941eb2dee480bfbde50a450b58a3c2
RUN git clone "${LITEX_REPO}" /src/golitex  && git -C /src/golitex checkout --detach "${LITEX_REF}"  && cargo build --release --manifest-path /src/golitex/Cargo.toml --bin litex

FROM python:3.12-slim
WORKDIR /app
COPY --from=litex-builder /src/golitex/target/release/litex /usr/local/bin/litex
COPY . /app
RUN python -m pip install --no-cache-dir .
ENV LITEX_BIN=/usr/local/bin/litex \
    LITEXPY_LITEX_BIN=/usr/local/bin/litex \
    LITEX_CHESS_TIMEOUT=45 \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "litex_chess.api:app", "--host", "0.0.0.0", "--port", "8000"]
