> **SUPERSEDED 2026-10-17 by [`../status/testing-protocol-v2.md`](../status/testing-protocol-v2.md).** v2 is v1 plus one parser fix: a verdict the model wraps in a JSON array is unwrapped and then validated as before (backlog **BL-125**). Nothing else changed. Do not run this version; its `-p1` run ids and the `memsoc-protocol-v1` tag are kept only so earlier partial runs stay readable.

# Test Protocol v1 — Memory Layer, Three LLMs

> **Who this is for:** the three testers, and the AI agent each of them uses. **Follow it exactly, top to bottom.**
>
> **Owner:** Aryan (memory layer). **Protocol version:** `p1`. **Code version:** git tag `memsoc-protocol-v1`. **Written:** 2026-10-16.
>
> **If anything happens that this document does not cover, stop and message Aryan. Do not improvise, do not "fix" code, do not retry in a different way.**

---

## 0. Instructions for the AI agent reading this

You are helping a tester run a fixed scientific experiment. The experiment is only valid if all three testers do **exactly** the same thing. So:

1. **Run only the commands written here, exactly as written.** Replace `<MODEL>` with the tester's value from §1 and nothing else.
2. **Never edit, create or delete any file in the repository.** The only exceptions are `.env` (§3.5) and the data you unzip into `artifacts\` (§3.4). This includes `src\`, `tests\`, `requirements\`, `docs\` and config files, even to "fix a bug".
3. **Never delete or modify anything under `artifacts\runs\` or `artifacts\memory\`.** Those are the results, and they cannot be regenerated identically.
4. **Never print, log, paste or commit the API key.**
5. **Do not create accounts, enter passwords or accept terms on the tester's behalf.** The tester does those steps (§3.5) themselves.
6. **Do not interpret or "improve" results.** Your job ends at sending the results zip (§6).
7. **When a step's output does not match the "Expected" text,** look it up in §7 *Troubleshooting*. If it is not there, stop and tell the tester to message Aryan with the last 30 lines of output.

---

## 1. What this test is, and your role

**The question:** when an LLM triages security alerts, does giving it a memory of similar past alerts make it more accurate? Each tester measures this for one LLM.

The program triages the **same first 165 alerts** three times, alert by alert:

| Arm | What the LLM sees | Run ID it writes |
|---|---|---|
| **A** | the alert only (no memory) | `armA-<tag>-p1` |
| **B-self** | the alert + its 3 most similar past alerts, with **the LLM's own earlier verdicts** | `bself-<tag>-p1` |
| **B-oracle** | the alert + the same 3 past alerts, with **the correct answers** | `boracle-<tag>-p1` |

**Your role — find your row and use exactly these values:**

| Tester | LLM | Provider | `<MODEL>` value | `<tag>` | API key needed |
|---|---|---|---|---|---|
| **Tester G** | `openai/gpt-oss-20b` | Groq | `gpt-oss-20b` | `gptoss20b` | `GROQ_API_KEY` |
| **Tester Q** | `qwen/qwen3.8-27b` | Groq | `qwen3.8-27b` | `qwen38-27b` | `GROQ_API_KEY` |
| **Tester M** | `gemma-4-26b-a4b-it` | Google AI Studio | `gemma-4-26b` | `gemma4-26b` | `GEMINI_API_KEY` |

**Expected duration:**

| Tester | Calls | Hands-on time | Running time |
|---|---|---|---|
| **M (Gemma)** | 495 | ~1 hour of setup | about **4–7 hours** in one sitting |
| **G and Q (Groq)** | 495 | ~1 hour of setup | about **4–8 days**, depending on tokens per call. Groq's free tier allows 200,000 tokens a day, about 70–130 calls. |

The program waits for the daily allowance by itself; you only keep it running (§4).

**Start order:**

| Tester | When to start |
|---|---|
| **M** | Any time. |
| **G** | Any time. **G is also the Groq check:** G's first verdicts show that the Groq setup works before Q spends any quota (§4.4). |
| **Q** | Only after Aryan sends Q the message **"Q: go"**. Aryan sends it after G's checkpoint (§4.4) looks right. Q may do all of §3, including `--preflight`, before that. |

---

## 2. What is held identical for all three testers (you change none of it)

| Item | Value | Enforced by |
|---|---|---|
| Code | git tag `memsoc-protocol-v1` | `--preflight` checks the checkout and that `src\`, `tests\`, `requirements\` are unmodified |
| Data | `artifacts\memsoc-protocol-v1-data.zip`, included in the repository at the tag: stream v2, 120,000 flows, seed 42, 1,135 detector alerts | `--preflight` checks three SHA-256 hashes |
| Alerts | the **first 165** in stream order | fixed in code; preflight checks their identity hash |
| Arms and order | for each alert: A, then B-self, then B-oracle | fixed in code |
| Prompt | the project's frozen triage prompt | preflight checks the hash of alert 0's prompt |
| LLM settings | temperature 0; max 6,000 output tokens; JSON answer mode; reasoning or thinking at the model's default | fixed in code; recorded in each `run_config.json` |
| Memory | `all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, CPU; ChromaDB 1.5.9; top 3; no similarity cut-off; every verdict stored; a fresh store per run | fixed in code; `--verify` compares retrieval against the reference machine |
| Python packages | Python 3.13; exact versions from `requirements\memory-protocol-v1-constraints.txt` | `--preflight` checks six key versions |
| Scoring | `memsoc.triage.score_verdicts`, unchanged | `--verify` runs it |

**Retries:** an answer that is not a valid verdict is retried up to 2 more times, and a dropped connection up to 10 times. Both are done the same way for every model, and the attempt count is recorded in each verdict row.

---

## 3. One-time setup (about 1 hour; almost all of it is downloads)

All commands are **Windows PowerShell**. Open PowerShell from the Start menu. Do **not** run it as Administrator.

### 3.1 Install Git and Python 3.13 (skip anything already installed)

1. **Git for Windows:** download from https://git-scm.com/download/win and install with the default options.
2. **Python 3.13 (64-bit):** download the latest 3.13.x "Windows installer (64-bit)" from https://www.python.org/downloads/windows/. In the installer, tick **"Add python.exe to PATH"**, then *Install Now*.
3. Close PowerShell, open a new one, and check:

```powershell
git --version
py -3.13 --version
```

**Expected:** `git version 2.x...` and `Python 3.13.x`. Any 3.13 is fine; 3.12 or 3.14 is **not**.

### 3.2 Get the code at the protocol version

```powershell
cd $env:USERPROFILE
git clone https://github.com/Heroic2024/Mem-SOC.git
cd Mem-SOC
git checkout memsoc-protocol-v1
```

**Expected:**
- The last command prints `HEAD is now at ...`.
- A note about **"detached HEAD"** is normal and correct. Do **not** create a branch and do not run `git pull`.

If `git clone` asks you to sign in or says the repository is not found, the repo is private: ask Aryan to add your GitHub account as a collaborator, then repeat.

### 3.3 Create the Python environment (outside the repo)

```powershell
py -3.13 -m venv "$env:USERPROFILE\.venvs\memsoc-memory"
& "$env:USERPROFILE\.venvs\memsoc-memory\Scripts\python.exe" -m pip install -r requirements\memory.txt -c requirements\memory-protocol-v1-constraints.txt
```

**Expected:** it downloads about 2 GB (torch is most of it) and ends with `Successfully installed ...`. This takes 5–20 minutes. Run it from inside `Mem-SOC`. Do **not** add or upgrade any package, and do **not** omit the `-c ...constraints.txt` part.

A `[notice] A new release of pip is available` line is normal. **Ignore it; do not upgrade pip.**

### 3.4 Put the data in place

The data bundle **`memsoc-protocol-v1-data.zip`** (21.5 MB) came with the code in §3.2, at `artifacts\memsoc-protocol-v1-data.zip`. Unpack it where it is:

```powershell
cd $env:USERPROFILE\Mem-SOC
Expand-Archive -Path artifacts\memsoc-protocol-v1-data.zip -DestinationPath artifacts -Force
Get-ChildItem artifacts, artifacts\model_outputs
```

**Expected:**
- `artifacts` contains `memsoc-protocol-v1-data.zip`, `generated_logs.jsonl` (~172 MB), `ground_truth.csv` (~4.3 MB) and `SHA256SUMS.txt`.
- `artifacts\model_outputs` contains `live_results.jsonl` (~30.6 MB).
- Leave the zip where it is. Do not delete or move it.

If `artifacts\memsoc-protocol-v1-data.zip` is missing, you are not on the tag: redo the `git checkout memsoc-protocol-v1` line of §3.2.

For reference, the zip's SHA-256 is `233567572d8de10446c9aac6562f96b085cfb8c19ddad8a35b86dadd07843376` (`Get-FileHash artifacts\memsoc-protocol-v1-data.zip`). Preflight checks the extracted files themselves.

### 3.5 Create your API key and the `.env` file (the tester does this, not the agent)

**Get a free key:**
- **Testers G and Q (Groq):** sign in at https://console.groq.com, open **API Keys**, then **Create API Key**. Stay on the free plan; do **not** add a payment method or upgrade.
- **Tester M (Google):** sign in at https://aistudio.google.com/apikey, then **Create API key**. Do **not** set up billing; the page must keep showing "Free tier".

**Use exactly one key, from your own account.** Do not use anyone else's key, and do not create extra accounts to get more quota.

**Write the key into `.env`.** The tester pastes their own key in place of `PASTE_KEY_HERE`. Use the line for your provider only.

```powershell
cd $env:USERPROFILE\Mem-SOC
# Testers G and Q:
Set-Content -Path .env -Value "GROQ_API_KEY=PASTE_KEY_HERE" -Encoding ascii
# Tester M:
Set-Content -Path .env -Value "GEMINI_API_KEY=PASTE_KEY_HERE" -Encoding ascii
```

`.env` is ignored by git. Never commit it, never share it, and never paste it into chat.

### 3.6 Preflight: check everything (one API call)

Run these three lines **every time you open a new PowerShell window** for this test:

```powershell
cd $env:USERPROFILE\Mem-SOC
$env:PYTHONPATH = "src"
$py = "$env:USERPROFILE\.venvs\memsoc-memory\Scripts\python.exe"
```

Then:

```powershell
& $py -m memsoc.triage.protocol_run --model <MODEL> --preflight
```

**Expected:**
- About 21 lines starting with `PASS` and a final line **`RESULT: PASS -- 0 check(s) failed`**.
- The first time, it also downloads the embedding model (~90 MB).
- It includes lines such as `PASS  git checkout is the protocol tag`, `PASS  data file generated_logs.jsonl`, `PASS  Arm A prompt for alert 0`, `PASS  API answers in JSON mode` and `PASS  local daily request budget`.

**Any `FAIL` line → do not start. Look it up in §7.**

---

## 4. Run the test

### 4.1 Start (or resume) the run

In a PowerShell window with the three setup lines from §3.6 already run:

```powershell
& $py -m memsoc.triage.protocol_run --model <MODEL>
```

**Expected:** it repeats the checks (all `PASS`), then prints one line per verdict:

```
[2026-10-17 10:00:05] gemma-4-26b-a4b-it: 0 of 495 verdicts already done; 495 to go
[2026-10-17 10:00:31] [1/495] alert 1/165 off    verdict=true_positive category=Fuzzers conf=0.9 precedents=0 tokens=2162 23s
[2026-10-17 10:01:02] [2/495] alert 1/165 self   verdict=true_positive category=Fuzzers conf=0.9 precedents=0 tokens=2162 24s
[2026-10-17 10:01:33] [3/495] alert 1/165 oracle verdict=true_positive category=Fuzzers conf=0.9 precedents=0 tokens=2162 24s
```

- `off`, `self` and `oracle` are Arms A, B-self and B-oracle.
- `precedents=0` on alert 1 is correct: memory starts empty. From alert 2 onward the memory arms show 1–3.
- Lines such as `server busy (503), waiting 15s` or `rate limited, waiting 8s` are **normal**. The program retries by itself.

### 4.2 Keep it running

- **Leave the window open.** Keep the laptop **plugged in**, and set *Settings → System → Power → Screen and sleep → "When plugged in, put my device to sleep after" → Never* for the duration.
- **When the daily allowance runs out,** you see:
  `Daily quota reached. Waiting 60 min, until about 14:30, then continuing automatically. Leave this window open.`
  - This is **expected** and is how the Groq runs spread over several days.
  - Do nothing. It continues by itself.
- **To check progress without disturbing the run,** open a **second** PowerShell window, run the three lines from §3.6, then:

```powershell
& $py -m memsoc.triage.protocol_run --model <MODEL> --status
```

**Expected:** three lines, `armA-<tag>-p1  N of 165 verdicts`, then the same for `bself` and `boracle`. The three numbers differ by at most 1.

- **If the window was closed, the PC restarted or slept, or you pressed Ctrl-C:** open PowerShell, run the three lines from §3.6, and run the §4.1 command again.
  - It resumes exactly where it stopped. Nothing is lost or repeated.
  - This is the **only** recovery procedure. Never delete files to "start clean".
- **Do not run anything else that uses the same API key** (another script, the dashboard, the report generator, a chat playground) until you finish. It eats the same daily allowance.

### 4.3 Daily check-in message to Aryan (Groq testers: once a day; Gemma tester: at the end)

Send the output of `--status`. Nothing else is needed unless something went wrong.

### 4.4 Tester G only — the Groq checkpoint (about 10 minutes after starting)

Your first verdicts are the check that the Groq setup works.

1. When the line starting **`[9/495]`** appears, copy the nine verdict lines `[1/495]` to `[9/495]`, plus any `ERROR`, `413`, `Request too large` or `json_validate_failed` lines above them.
2. Send them to Aryan with the subject **"G checkpoint"**.
3. **Keep the run going.** Do not stop it unless Aryan tells you to.

If the run stops with an error **before** `[9/495]`:
- Follow §7.
- Send Aryan the last 30 lines with the subject **"G checkpoint failed"**.

Aryan then tells Q either "Q: go" or to wait.

---

## 5. Exit codes — what the program's ending means

| Last line you see | Exit code | Meaning | What to do |
|---|---|---|---|
| `DONE: all 495 verdicts written. Next: run with --verify.` | 0 | Finished | Go to §6 |
| `Stopped by Ctrl-C ...` | 130 | You stopped it | Run §4.1 again when ready |
| `ERROR on alert ...` | 1 | Something failed after the built-in retries | §7, row "ERROR on alert" |
| `Not starting: fix the FAIL lines above` | 1 | A check failed | §7, the matching FAIL row |
| `... was started under different settings ...` | 1 | The code, model or data changed mid-run | **Stop. Message Aryan.** Do not delete anything |
| `Daily quota reached ... Run the same command again after the quota resets.` | 2 | Only appears with `--no-wait`, which this protocol never uses | Run §4.1 again later |

---

## 6. Finish: verify and send the results

### 6.1 Verify

```powershell
& $py -m memsoc.triage.protocol_run --model <MODEL> --verify
```

**Expected:** every line `PASS`, ending `RESULT: PASS -- 0 check(s) failed`, followed by three score reports (one per arm) from `score_verdicts`.

A `WARN` on `retrieval matches the reference machine` is acceptable: package anyway, and mention the number in your message. Any `FAIL` means **do not package**; send the full output to Aryan.

### 6.2 Package and send

```powershell
& $py -m memsoc.triage.protocol_run --model <MODEL> --package
```

**Expected:** it re-runs the verification, then prints
`PACKAGED: ...\Mem-SOC\artifacts\memsoc-p1-<tag>-results.zip  (N MB). Send this file to Aryan.`

Send Aryan:
1. **The zip file:** `artifacts\memsoc-p1-<tag>-results.zip`. It contains all three runs, both memory stores, each `run_config.json` and the full log.
2. **The full console output of `--verify`,** pasted into the message.

Then you are done. **Do not delete** the `Mem-SOC` folder until Aryan confirms receipt.

---

## 7. Troubleshooting

| Symptom | Action |
|---|---|
| `FAIL Python 3.13` | Install Python 3.13 (§3.1), then redo §3.3 to recreate the environment with `py -3.13`. |
| `FAIL chromadb==...`, `torch==...` or any other package line | The environment was built differently. Run `Remove-Item -Recurse -Force "$env:USERPROFILE\.venvs\memsoc-memory"` (this only removes the Python environment, never results), then redo §3.3 exactly. |
| `FAIL git checkout is the protocol tag` | `cd $env:USERPROFILE\Mem-SOC` then `git checkout memsoc-protocol-v1`. If git refuses, stop and message Aryan. |
| `FAIL no local changes to src/, tests/, requirements/` | Someone edited code. **Do not run.** Send Aryan the output of `git status` and `git diff --stat`. |
| `FAIL data file ...` (missing or wrong hash) | Re-download the zip and redo §3.4. If it still fails, message Aryan. |
| `FAIL 1135 detector alerts`, `first 165 alerts`, `Arm A prompt for alert 0` or `every alert joins its flow` | Wrong data or code. Redo §3.2 and §3.4. If it persists, message Aryan. |
| `FAIL embedding model loads` | The first run needs internet access to huggingface.co. Check the connection and run preflight again. If it fails twice, message Aryan with the line. |
| `FAIL GROQ_API_KEY in .env` or `GEMINI_API_KEY in .env` | Redo §3.5. The file must be named exactly `.env`, in the `Mem-SOC` folder. |
| `FAIL API answers in JSON mode` with `401` or `invalid api key` | The key is wrong or was deleted. Create a new key (§3.5) and preflight again. |
| `FAIL API answers in JSON mode` with `429` | The quota is busy. Wait 15 minutes and run preflight again. |
| `FAIL API answers in JSON mode` with `404`, `model not found` or `decommissioned` | The provider removed the model. **Stop. Message Aryan.** Do not switch models. |
| `FAIL API answers in JSON mode`, anything else | Message Aryan with the line. |
| `FAIL local daily request budget` | Today's allowance is used up. Try again tomorrow. |
| `413`, `Request too large` or `json_validate_failed` anywhere in the output | **Stop the run (Ctrl-C) if it is still going, and message Aryan** with the last 30 lines. Do not retry. These mean the Groq settings themselves need a decision. |
| `ERROR on alert ...` (the run stopped) | Copy the last 30 lines. Wait 10 minutes, then run §4.1 once more. If it stops again with the same error, **stop** and send Aryan both outputs. |
| Many `server busy` or `rate limited` lines, but verdict lines keep appearing | Normal. Do nothing. |
| `Daily quota reached. Waiting ...` | Normal. Do nothing; leave the window open. |
| `WARNING: N memory writes failed` | Finish the run, then mention it to Aryan with your results. |
| `--status` numbers differ by more than 1 | Message Aryan with the output. Do not delete anything. |
| Anything not in this table | **Stop and message Aryan** with the last 30 lines. Do not improvise. |

---

## 8. Never do these (each one silently invalidates the comparison)

- Never edit any file in `src\`, `tests\`, `requirements\` or `docs\`, or the prompt or any setting, even to fix an error.
- Never change `<MODEL>`, use another model "because it is faster", or add flags not shown here.
- Never delete, move, rename or edit anything in `artifacts\runs\` or `artifacts\memory\`, and never "start over".
- Never re-run or remove an individual verdict.
- Never use a paid tier, add billing, use extra accounts or keys, or share a key between testers.
- Never run other programs on the same API key while the test runs.
- Never look at the verdicts and change anything in response. A bad-looking result is a valid result.
- Never `git commit`, `git push` or `git pull` in this checkout.

---

## 9. What gets measured (for understanding only; testers do not analyse)

Aryan analyses all three models together after receiving the zips. Every alert is a real attack, so:

- **Escalation rate:** the share of the 165 alerts the LLM correctly called a real attack (`true_positive`), per arm.
- **Family accuracy:** the share where it named the right attack family, per arm, beside the detector's own 82.4% on these alerts.
- **Paired tests:** exact McNemar, B-self vs A and B-oracle vs A, on the same alerts.
- **Memory effect:** whether B-self improves on A (deployable memory), and how far B-oracle does (the ceiling with correct labels).
- **Retrieval quality:** whether the retrieved past alerts are the same family, the same for every model by construction (§2).
- **Cost:** tokens and seconds per verdict.

---

## 10. For Aryan only — release checklist and afterwards (testers skip this)

**Done 2026-10-16:**
- Code, this document and the data zip are committed on branch `aryan`.
- The tag `memsoc-protocol-v1` is pushed.
- The Gemma smoke run (2 alerts × 3 arms) passed preflight, verify and package.

**Still to do before testers start:**
1. Add the three testers as collaborators on the private GitHub repo `Heroic2024/Mem-SOC`.
2. Send each tester this document's path in the repo and their row from §1.

**The Groq check is delegated to Tester G.** Aryan could not create a Groq key (BL-120), so G's first 9 verdicts serve as the check (§4.4). When G's checkpoint arrives, confirm three things:
- Nine verdict lines, with no `413`, `Request too large` or `json_validate_failed`. This shows JSON mode and the 6,000-token cap fit Groq's 8K TPM.
- The `tokens=` values. Total days ≈ 495 ÷ (200,000 ÷ average tokens per call).
- G's daily `--status` count, which shows empirically whether Groq also counts the `max_tokens` reservation against the daily token limit. Roughly 25–30 verdicts a day would mean it does, about 3 weeks in total.

If all is well, send Q "Q: go". If not, tell G to stop and decide the fix before anyone continues. Any code change means a new protocol version, and G's partial run is then discarded.

**When the zips arrive:**
1. Unzip each into the repo's `artifacts\`. The zip is laid out as `runs\...` and `memory\...`.
2. Run `--verify --model <each>` locally.
3. Analyse in `notebooks/retrieval-quality.ipynb` (BL-123).
