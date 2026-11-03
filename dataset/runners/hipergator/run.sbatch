#!/usr/bin/env bash
# Serve the model on one 4xB200 node (Apptainer, pinned vLLM image) and process a prepared run.
# Submit from dataset/:
#   sbatch --account=ACCOUNT --qos=ACCOUNT runners/hipergator/run.sbatch RUN WEIGHTS SIF [CONFIG]
# WEIGHTS holds model/ and draft/ (see `ehr-dataset weights`); SIF is the vLLM image from configs/beam.yaml
# (apptainer build beam.sif docker://vllm/vllm-openai@sha256:...).
#SBATCH --job-name=ehr-dataset
#SBATCH --partition=hpg-b200
#SBATCH --gres=gpu:b200:4
#SBATCH --cpus-per-task=16
#SBATCH --mem=200G
#SBATCH --time=12:00:00
#SBATCH --output=ehr-dataset-%j.log
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
RUN=$(realpath "$1"); WEIGHTS=$(realpath "$2"); SIF=$(realpath "$3"); CONFIG=$(realpath "${4:-configs/beam.yaml}")
module load apptainer java
PORT=$((20000 + RANDOM % 20000))
LOG="$RUN/server-$SLURM_JOB_ID.log"
.venv/bin/ehr-dataset serve --config "$CONFIG" --weights "$WEIGHTS" --gpus "$CUDA_VISIBLE_DEVICES" --port "$PORT" \
  --apptainer "$SIF" --cache "$RUN/.serving-cache" > "$LOG" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; wait $SERVER 2>/dev/null || true' EXIT
# Loading ~290 GB of weights and compiling takes 20-30 minutes.
for _ in $(seq 1 540); do
  curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null && break
  kill -0 $SERVER 2> /dev/null || { echo 'vLLM exited during startup'; tail -50 "$LOG"; exit 1; }
  sleep 10
done
curl -sf "http://127.0.0.1:$PORT/v1/models" > /dev/null || { echo 'vLLM did not become ready'; exit 1; }
.venv/bin/ehr-dataset run --run "$RUN" --endpoint "http://127.0.0.1:$PORT/v1"
.venv/bin/ehr-dataset status --run "$RUN"
