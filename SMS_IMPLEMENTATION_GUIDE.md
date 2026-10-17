# SMS Notification Implementation Guide

## API key location

Open the project `.env` file and set:

```env
SMS_ENABLED=True
SMS_API_URL=https://smsapiph.onrender.com/api/v1/send/sms
SMS_API_KEY=YOUR_REAL_API_KEY
SMS_BATCH_SIZE=5
SMS_MAX_RETRIES=3
```

Never paste the key into `settings.py`, Git, screenshots, or chat messages.

## Database

The `sms_notifications` table follows Table 3.8 of the capstone data
dictionary:

- `sms_id`
- `user_id`
- `phone_number`
- `message_text`
- `sms_type`
- `reference_id`
- `status`
- `sent_at`
- `created_at`
- `retry_count`

The phone number is stored as text because integer fields destroy a leading
zero and cannot represent the `+63` prefix correctly.

## Implemented automatic events

- District Supervisor announcement
- Principal school announcement
- Teacher class announcement
- Newly published Module
- Newly published Activity
- Module and Activity deadline near (2 to 3 days)
- Module and Activity deadline tomorrow
- Module and Activity deadline today
- Released term grade

Drafts and repeated Publish clicks do not create duplicate SMS records.
Deadline SMS messages are skipped when the learner already submitted or was
graded.

## Required phone-number format

Users register their phone number through the existing My Profile page.
Accepted values include `09171234567`, `639171234567`, and `+639171234567`.
The provider receives the normalized form `+639171234567`.

## Safe first test

1. Keep `SMS_ENABLED=False` while checking the interface.
2. Put only your own mobile number in your test account.
3. Add the real API key to `.env`.
4. Change `SMS_ENABLED=True`.
5. Restart the Django server so settings are reloaded.
6. Publish one test announcement.
7. Confirm a pending row exists in Django Admin under SMS notifications.
8. Run:

```powershell
C:\Users\lacun\django-env\Scripts\python.exe manage.py send_pending_sms
```

9. Confirm that the row changes from `pending` to `sent`.

## Automatic Windows scheduling

Create one Windows Task Scheduler task with:

- Program: `C:\Users\lacun\django-env\Scripts\python.exe`
- Arguments: `manage.py process_sms_jobs`
- Start in: `C:\Users\lacun\django-env\DepedLMS`
- Repeat task every: `1 minute`
- Duration: `Indefinitely`

The command sends at most five SMS messages per execution to stay under the
provider's published six-per-minute limit.

## Useful commands

```powershell
python manage.py check
python manage.py send_deadline_notifications
python manage.py send_pending_sms
python manage.py process_sms_jobs
```

Do not run `send_pending_sms` until the API key is configured and the account
has sufficient service availability or credits.
