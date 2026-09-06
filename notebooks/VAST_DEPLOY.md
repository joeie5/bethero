# Training on Vast.ai — deployment guide

One rented box, no per-account secrets dance, no free-tier disconnects.
Real SSH server, so it runs unattended for the whole job.

## 1. Rent the instance

vast.ai/console — filter `#GPUs: 1X`, `RTX 4090`, `On-Demand` (not
Interruptible — that can be reclaimed mid-job, defeating the point of this
move). Look for 16+ CPU threads, NVMe storage, ≥97% reliability, verified.
`m:41013` (Quebec, 32 threads, $0.375/hr, 99.14% reliability) is a solid pick
as of this writing — the listing itself will have changed by the time you
read this, re-check against the same criteria.

## 2. SSH in

Vast.ai gives you the exact SSH command on the instance's console page
(something like `ssh -p <port> root@<host>`). Use it directly — no key setup
needed if the instance shows an SSH command ready to copy.

## 3. Clone the repo

```bash
git clone https://<GITHUB_TOKEN>@github.com/joeie5/bethero.git
cd bethero
```

Replace `<GITHUB_TOKEN>` with a fine-grained GitHub token scoped to this repo
("Contents: Read-only" is enough) — same one used for the Colab notebooks,
if you still have it.

## 4. Upload the data snapshot and `.env`

From your **local machine** (not the Vast.ai box), in a separate terminal:

```bash
scp -P <port> -r data_snapshot/ root@<host>:~/bethero/data_snapshot/
scp -P <port> .env root@<host>:~/bethero/.env
```

`.env` just needs `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` —
`app/config.py` loads it automatically via pydantic-settings, no Colab-style
per-secret setup required.

## 5. Run setup

Back on the Vast.ai box:

```bash
chmod +x scripts/vast_setup.sh
./scripts/vast_setup.sh
```

This installs the training-only dependencies (not the full `requirements.txt`
— see the script's comments for why), verifies CUDA is visible, and checks
`data_snapshot/`/`.env` are both present before you go any further.

## 6. Launch training inside tmux (survives SSH disconnects)

```bash
tmux new -s training
python3 scripts/vast_train.py --markets all --n-trials 20
```

Then **Ctrl+B, then D** to detach — training keeps running on the server even
after you close the SSH connection or your laptop sleeps. Reconnect anytime
with:

```bash
tmux attach -t training
```

**Prefer plain `nohup` over tmux?** Works too:

```bash
nohup python3 scripts/vast_train.py --markets all --n-trials 20 > train.log 2>&1 &
tail -f train.log     # Ctrl+C to stop watching, the job keeps running
```

## 7. Resumability

`vast_train.py` skips any market that already has a saved
`StackingEnsemble_football_<market>.joblib` in `models/` — same as the
Colab notebooks. If the box itself ever reboots (rare on On-Demand, but
possible), just re-run the same command; finished markets are skipped
automatically.

## 8. Get the trained models back

```bash
# from your LOCAL machine
scp -P <port> -r root@<host>:~/bethero/models/ ./models_from_vast/
```

Then merge into your local `models/` the same way the Colab zip outputs were
merged.

## 9. Stop the instance

**Don't forget this** — Vast.ai bills until you stop it. Once you've pulled
the models down and confirmed they're intact, stop the instance from the
Vast.ai console.
