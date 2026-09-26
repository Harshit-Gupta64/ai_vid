# Windows Task Scheduler Setup Guide: Local Pipeline (3x Daily)

This guide documents how to register the **ai_vid** local production pipeline with Windows Task Scheduler to run automatically 3 times per day.

---

## 1. Schedule Architecture

The cloud pipeline runs 4x daily via GitHub Actions at:
- **00:00 UTC** (05:30 IST)
- **06:00 UTC** (11:30 IST)
- **12:00 UTC** (17:30 IST)
- **18:00 UTC** (23:30 IST)

The **local Windows pipeline** is staggered to run 3x daily during active hours:
- **09:00 AM Local** (Morning run)
- **03:00 PM Local** (Afternoon run)
- **09:00 PM Local** (Evening run)

Both pipelines query the same **Turso libSQL database**, claiming unclaimed topics using atomic row locks so they will **never** collide or double-produce the same video.

---

## 2. Quick Setup via Command Prompt / PowerShell (Recommended)

Open **PowerShell** or **Command Prompt as Administrator** and run the following three commands:

```cmd
:: Morning Run (09:00 AM)
schtasks /create /tn "AiVid_Morning_0900" /tr "C:\Users\Harshit\AppData\Local\Programs\Python\Python311\python.exe C:\Projects\Videos\scripts\run_local_scheduled.py" /sc daily /st 09:00 /ru "%USERNAME%"

:: Afternoon Run (03:00 PM)
schtasks /create /tn "AiVid_Afternoon_1500" /tr "C:\Users\Harshit\AppData\Local\Programs\Python\Python311\python.exe C:\Projects\Videos\scripts\run_local_scheduled.py" /sc daily /st 15:00 /ru "%USERNAME%"

:: Evening Run (09:00 PM)
schtasks /create /tn "AiVid_Evening_2100" /tr "C:\Users\Harshit\AppData\Local\Programs\Python\Python311\python.exe C:\Projects\Videos\scripts\run_local_scheduled.py" /sc daily /st 21:00 /ru "%USERNAME%"
```

> **Note:** If your `python.exe` is located elsewhere, verify its path with `where python` in PowerShell and replace the path above.

To verify the tasks were registered successfully:
```cmd
schtasks /query /tn AiVid_Morning_0900
schtasks /query /tn AiVid_Afternoon_1500
schtasks /query /tn AiVid_Evening_2100
```

To delete the tasks if needed later:
```cmd
schtasks /delete /tn "AiVid_Morning_0900" /f
schtasks /delete /tn "AiVid_Afternoon_1500" /f
schtasks /delete /tn "AiVid_Evening_2100" /f
```

---

## 3. Alternative GUI Setup (Task Scheduler App)

If you prefer using the graphical Windows interface:

1. Press `Win + R`, type `taskschd.msc`, and press **Enter**.
2. In the right-hand panel, click **Create Task...** (not *Create Basic Task*).
3. **General Tab**:
   - **Name**: `AiVid_Local_Scheduled`
   - Select **Run only when user is logged on** (or *Run whether user is logged on or not* with credentials saved).
   - Check **Run with highest privileges**.
4. **Triggers Tab**:
   - Click **New...**
   - Begin the task: **On a schedule** -> **Daily**
   - Set **Start**: Today's date, `09:00:00`
   - Repeat this to add triggers for `15:00:00` and `21:00:00`.
5. **Actions Tab**:
   - Click **New...**
   - Action: **Start a program**
   - Program/script: `python` (or full path `C:\Users\Harshit\AppData\Local\Programs\Python\Python311\python.exe`)
   - Add arguments: `scripts\run_local_scheduled.py`
   - Start in (optional): `C:\Projects\Videos`
6. **Conditions Tab**:
   - Uncheck *Start the task only if the computer is on AC power* (if on a laptop).
   - Check *Wake the computer to run this task* (optional, recommended).
7. **Settings Tab**:
   - Check *Allow task to be run on demand*.
   - Check *Stop the task if it runs longer than*: `1 hour`.
8. Click **OK** to save.

---

## 4. Testing the Scheduled Task Immediately

You can trigger a test run anytime without waiting for the scheduled time:

```cmd
schtasks /run /tn "AiVid_Morning_0900"
```
Or directly in PowerShell:
```powershell
python scripts\run_local_scheduled.py
```
