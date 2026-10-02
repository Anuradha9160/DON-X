FROM mysterysd/wzmlx:wzadv
COPY --from=mysterysd/wzmlx:m-tools /usr/local /usr/local
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /usr/src/app

COPY requirements.txt .
RUN uv pip install --python /wzvenv/bin/python --no-cache-dir -r requirements.txt
RUN uv pip install --python /wzvenv/bin/python --no-cache-dir --no-deps "mega.py>=1.0.8"

COPY . .

ENTRYPOINT ["bash", "start.sh"]
