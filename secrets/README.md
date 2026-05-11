# Secrets

Place local secret files here when Docker Compose needs file-based secrets.

Do not commit real secrets. Keep only this README in version control.

Create local files from the examples:

```powershell
Copy-Item secrets/hf_token.txt.example secrets/hf_token.txt
```

`hf_token.txt` is mounted into containers as:

```text
/run/secrets/hf_token
```

API and training code should read secrets from `/run/secrets/<name>`, not from Docker image layers or committed `.env` files.
