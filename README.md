# ClockBot – Setup & Run Guide (Mac)

## 📁 Files
```
humanforce_agent/
├── clockbot.py        ← main agent
├── .env               ← your credentials (private)
├── requirements.txt   ← dependencies
├── screenshots/       ← auto-created, proof of each action
└── clockbot.log       ← auto-created, full activity log
```

---

## ⚙️ One-Time Setup (5 minutes)

### Step 1 – Install Python (if not already)
```bash
brew install python
```

### Step 2 – Open Terminal, navigate to the folder
```bash
cd ~/humanforce_agent
```

### Step 3 – Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 4 – Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 5 – Add your credentials to `.env`
Open `.env` and replace the placeholder values:
```
HF_EMPLOYEE_CODE=12345
HF_PASSWORD=yourpassword
```

---

## ▶️ Run the Agent

```bash
source venv/bin/activate
python clockbot.py
```

Keep this terminal window open (or run it in background — see below).

---

## 🔁 Run in Background (so you can close Terminal)

```bash
nohup python clockbot.py > /dev/null 2>&1 &
echo $! > clockbot.pid
```

To stop it later:
```bash
kill $(cat clockbot.pid)
```

---

## 🧪 Test Immediately (without waiting for schedule)

In `clockbot.py`, uncomment these two lines near the bottom:
```python
# log.info("Running immediate test clock-in …")
# job_clock_in()
```
Then run the script — it will clock in right away so you can verify it works.

---

## 📸 Verify It Worked

After each run, check:
- `screenshots/` folder — a PNG is saved after every action
- `clockbot.log` — full log of every action and any errors
- Mac notification — a desktop alert appears on success or failure

---

## 🔧 Troubleshooting

| Problem | Fix |
|---------|-----|
| "Could not find clock-in button" | Check the screenshot — the button text may differ. Update `patterns` list in `_do_clock_action()` |
| Login fails | Double-check `.env` credentials |
| Script stops after Mac sleep | Set Mac to not sleep: System Settings → Battery → Prevent sleep |
| Want it to auto-start on reboot | Add to Mac Login Items or create a launchd plist |

---

## 💤 Keep Mac Awake at Night (important!)

For the 10 PM clock-out to work, your Mac must be awake.
Run this once to prevent sleep:
```bash
caffeinate -i python clockbot.py
```
This keeps the Mac awake as long as the script is running.
