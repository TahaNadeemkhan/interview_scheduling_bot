import chainlit as cl
import os
import asyncio
from agents import Agent, Runner, AsyncOpenAI, OpenAIChatCompletionsModel, function_tool
from openai.types.responses import ResponseTextDeltaEvent
from agents.run import RunConfig
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from datetime import datetime, timedelta, timezone 
import pickle
from google.auth.transport.requests import Request
from typing import Any, List, Dict 
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText

# Loading environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")
EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
if not EMAIL_SENDER or not EMAIL_PASSWORD:
    print("Warning: EMAIL_SENDER or EMAIL_PASSWORD not found in environment variables. Email notifications will not be sent.")

CREDENTIALS_FILE = 'credentials.json'
TOKEN_PICKLE_FILE = 'token.pickle'
GOOGLE_CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']
RECRUITER_EMAIL = 'tahak6884@gmail.com' 
DEFAULT_CALENDAR_ID = 'primary'
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/" 
GEMINI_MODEL = "gemini-2.0-flash" 

# Google Calendar Setup
def setup_calendar_api() -> Any:
    """Set up the Google Calendar API service with token persistence."""
    creds = None
    if os.path.exists(TOKEN_PICKLE_FILE):
        try:
            with open(TOKEN_PICKLE_FILE, 'rb') as token:
                creds = pickle.load(token)
        except (EOFError, pickle.UnpicklingError):
            print(f"Warning: Could not load token from {TOKEN_PICKLE_FILE}. Will re-authenticate.")
            creds = None 

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("Refreshing Google API token...")
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}. Need to re-authenticate.")
                creds = None 
                if os.path.exists(TOKEN_PICKLE_FILE):
                    os.remove(TOKEN_PICKLE_FILE)
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"Error: '{CREDENTIALS_FILE}' not found. Please download it from Google Cloud Console.")
                return None
            try:
                print(f"Performing Google OAuth flow using {CREDENTIALS_FILE}...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    CREDENTIALS_FILE, GOOGLE_CALENDAR_SCOPES
                )
                creds = flow.run_local_server(port=0)
                print("Authentication successful.")
            except FileNotFoundError:
                print(f"Error: '{CREDENTIALS_FILE}' file not found.")
                return None
            except Exception as e:
                print(f"Error during OAuth flow: {e}")
                return None 

        if creds:
            try:
                with open(TOKEN_PICKLE_FILE, 'wb') as token:
                    pickle.dump(creds, token)
                print(f"Credentials saved to {TOKEN_PICKLE_FILE}")
            except Exception as e:
                print(f"Error saving token to {TOKEN_PICKLE_FILE}: {e}")

    if creds and creds.valid:
        try:
            service = build('calendar', 'v3', credentials=creds)
            print("Google Calendar service created successfully.")
            return service
        except Exception as e:
            print(f"Error building Google Calendar service: {e}")
            return None
    else:
        print("Could not obtain valid credentials.")
        return None

# Initialize service once, it is global
google_calendar_service = setup_calendar_api() 

# Email Sending Function 
def send_email(recipient_email: str, subject: str, body: str):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print(f"Cannot send email to {recipient_email}. Sender credentials not configured.")
        return

    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = recipient_email

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, recipient_email, msg.as_string())
        print(f"Email sent successfully to {recipient_email}")
    except Exception as e:
        print(f"Error sending email to {recipient_email}: {e}")


@function_tool
def get_free_slots(calendar_id: str = DEFAULT_CALENDAR_ID, days_ahead: int = 14) -> List[Dict[str, str]]:
    """
    Get free time slots from the calendar for the upcoming specified number of days (default 14).
    It only considers times between 9 AM to 5 PM in the calendar's timezone (approximated as UTC).
    Returns a list of available slots like [{'start': 'YYYY-MM-DDTHH:MM:SSZ', 'end': 'YYYY-MM-DDTHH:MM:SSZ'}, ...].
    """
    if not google_calendar_service:
        print("Error: Google Calendar service not available.")
        return {"error": "Google Calendar service not available. Cannot fetch slots."}

    now = datetime.now(timezone.utc)
    time_min_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    time_max_dt = time_min_dt + timedelta(days=days_ahead)
    time_min = time_min_dt.isoformat()
    time_max = time_max_dt.isoformat()
    print(f"Current UTC time: {now}")

    print(f"Checking calendar '{calendar_id}' for free slots between {time_min} and {time_max}")

    try:
        events_result = google_calendar_service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        print(f"Calendar events: {events}")
    except HttpError as error:
        print(f"An error occurred fetching calendar events: {error}")
        return {"error": f"Could not fetch calendar events: {error}"}
    except Exception as e:
        print(f"An unexpected error occurred fetching calendar events: {e}")
        return {"error": f"An unexpected error occurred fetching calendar events: {e}"}

    try:
        calendar_meta = google_calendar_service.calendars().get(calendarId=calendar_id).execute()
        calendar_tz_str = calendar_meta.get('timeZone', 'UTC') 
        print(f"Calendar timezone: {calendar_tz_str} (Calculations proceeding assuming UTC for simplicity)")
    except HttpError as error:
        print(f"Warning: Could not fetch calendar timezone: {error}. Defaulting to UTC.")
        calendar_tz_str = 'UTC' 

    busy_slots = []
    for event in events:
        start_str = event['start'].get('dateTime')
        end_str = event['end'].get('dateTime')
        if not start_str or not end_str:
            start_date_str = event['start'].get('date') 
            end_date_str = event['end'].get('date')
            if start_date_str:
                try:
                    start_dt_naive = datetime.strptime(start_date_str, '%Y-%m-%d')
                    busy_start_utc = start_dt_naive.replace(hour=9, minute=0, second=0, tzinfo=timezone.utc)
                    busy_end_utc = start_dt_naive.replace(hour=17, minute=0, second=0, tzinfo=timezone.utc)

                    if busy_start_utc < time_max_dt or busy_end_utc > time_min_dt:
                        busy_slots.append({
                            'start': max(busy_start_utc, time_min_dt),
                            'end': min(busy_end_utc, time_max_dt)
                        })
                except ValueError:
                    print(f"Could not parse all-day event date: {start_date_str}")
                continue 
        try:
            start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))

            start_dt_utc = start_dt.astimezone(timezone.utc)
            end_dt_utc = end_dt.astimezone(timezone.utc)

            busy_slots.append({'start': start_dt_utc, 'end': end_dt_utc})
        except ValueError:
            print(f"Could not parse event time: start='{start_str}', end='{end_str}'")
            continue 

    busy_slots.sort(key=lambda x: x['start'])

    free_slots = []
    current_check_time = time_min_dt 

    while current_check_time < time_max_dt:
        day_start_working_utc = current_check_time.replace(hour=9, minute=0, second=0, microsecond=0)
        day_end_working_utc = current_check_time.replace(hour=17, minute=0, second=0, microsecond=0)


        current_potential_start = max(day_start_working_utc, time_min_dt) 
        current_day_end = min(day_end_working_utc, time_max_dt) 

        relevant_busy = [
            slot for slot in busy_slots
            if slot['start'] < current_day_end and slot['end'] > current_potential_start 
        ]

        for busy_slot in relevant_busy:
            busy_start = busy_slot['start']
            busy_end = busy_slot['end']

            effective_busy_start = max(busy_start, day_start_working_utc)
            effective_busy_end = min(busy_end, day_end_working_utc)

            if current_potential_start < effective_busy_start:
                free_start = max(current_potential_start, day_start_working_utc) 
                free_end = min(effective_busy_start, day_end_working_utc) 
                if free_start < free_end: 
                    free_slots.append({
                        'start': free_start.isoformat().replace('+00:00', 'Z'),
                        'end': free_end.isoformat().replace('+00:00', 'Z')
                    })

            current_potential_start = max(current_potential_start, effective_busy_end)

        if current_potential_start < current_day_end:
            free_slots.append({
                'start': current_potential_start.isoformat().replace('+00:00', 'Z'),
                'end': current_day_end.isoformat().replace('+00:00', 'Z') 
            })

        current_check_time = current_check_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        print(f"Generated free slots: {free_slots}")
        
    if not free_slots:
        print("No free slots found in the next 14 days between 9 AM to 5 PM UTC.")
        return [] 

    print(f"Found {len(free_slots)} free slots.")
    print(f"Generated free slots: {free_slots}")
    return free_slots



@function_tool
def book_interview(start_time: str, end_time: str, candidate_email: str, calendar_id: str = DEFAULT_CALENDAR_ID) -> str:
    """
    Book an interview slot on the calendar.
    Requires start_time and end_time in ISO format (e.g., '2026-04-15T10:00:00Z')
    and the candidate's email address.
    """
    if not google_calendar_service:
        print("Error: Google Calendar service not available.")
        return "Failed to book interview: Google Calendar service not available."

    try:
        datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        datetime.fromisoformat(end_time.replace('Z', '+00:00'))
    except ValueError:
            return f"Failed to book interview: Invalid start_time ('{start_time}') or end_time ('{end_time}') format. Use ISO format (YYYY-MM-DDTHH:MM:SSZ)."

    if not candidate_email or '@' not in candidate_email:
            return f"Failed to book interview: Invalid candidate_email ('{candidate_email}')."

    event = {
        'summary': f'Interview with {candidate_email}',
        'description': 'Interview scheduled via automated bot.',
        'start': {'dateTime': start_time, 'timeZone': 'UTC'},
        'end': {'dateTime': end_time, 'timeZone': 'UTC'},
        'attendees': [
            {'email': candidate_email},
            {'email': RECRUITER_EMAIL} 
        ],
         'reminders': {
             'useDefault': False,
             'overrides': [
                 {'method': 'email', 'minutes': 24 * 60},
                 {'method': 'popup', 'minutes': 30},     
             ],
         },
    }

    try:
        print(f"Attempting to book interview for {candidate_email} from {start_time} to {end_time}")
        created_event = google_calendar_service.events().insert(
            calendarId=calendar_id,
            body=event,
            sendNotifications=True
            ).execute()
        print(f"Interview booked successfully! Event ID: {created_event.get('id')}")

        # Send Email Notifications 
        subject = "Interview Scheduled"
        body_candidate = f"""
        Dear Candidate,

        Your interview has been successfully scheduled for:
        Date: {datetime.fromisoformat(start_time.replace('Z', '+00:00')).strftime('%Y-%m-%d')}
        Time: {datetime.fromisoformat(start_time.replace('Z', '+00:00')).strftime('%I:%M %p')} UTC to {datetime.fromisoformat(end_time.replace('Z', '+00:00')).strftime('%I:%M %p')} UTC.

        We look forward to meeting you!

        Best regards,
        The Hiring Team
        """
        send_email(candidate_email, subject, body_candidate)

        body_recruiter = f"""
        Dear Recruiter,

        An interview has been scheduled with {candidate_email} for:
        Date: {datetime.fromisoformat(start_time.replace('Z', '+00:00')).strftime('%Y-%m-%d')}
        Time: {datetime.fromisoformat(start_time.replace('Z', '+00:00')).strftime('%I:%M %p')} UTC to {datetime.fromisoformat(end_time.replace('Z', '+00:00')).strftime('%I:%M %p')} UTC.

        The event has been added to the calendar.

        Best regards,
        The Interview Scheduling Bot
        """
        send_email(RECRUITER_EMAIL, subject, body_recruiter)

        return f"Success! Interview booked for {candidate_email} starting {start_time} and ending {end_time}."
    except HttpError as error:
        error_content = "Unknown error"
        try:
            # Try to get more details from the error response
            error_content = error.resp.get('content', '{}')
        except Exception:
            pass 
        print(f"An error occurred booking the interview: {error}. Details: {error_content}")
        if error.resp.status == 409:
            return f"Failed to book interview: This time slot ({start_time}) might already be booked or clash with another event. Please try choosing another slot."
        return f"Failed to book interview due to a calendar API error: {error}. Details: {error_content}"
    except Exception as e:
        print(f"An unexpected error occurred booking the interview: {e}")
        return f"Failed to book interview due to an unexpected error: {str(e)}"


#Agent and Model Setup
# Initialize OpenAI client 
provider = AsyncOpenAI(
    api_key=GEMINI_API_KEY,
    base_url=GEMINI_BASE_URL
)

model = OpenAIChatCompletionsModel(
    model=GEMINI_MODEL,
    openai_client=provider
)

config = RunConfig(
    model=model,
    model_provider=provider,
    tracing_disabled=True 
)

# Set up Agent  
agent = Agent(
    name="Interview Scheduling Bot",
    instructions='''You are an expert interview scheduling bot using Google Calendar. Your goal is to help candidates find and book an interview slot efficiently and naturally.
1. Greet & Offer: Start by greeting the candidate and asking if they want to find an interview slot.
2. Fetch Slots: If they agree, use the 'get_free_slots' tool.
    - IMPORTANT: When calling 'get_free_slots', rely on the default parameters. Do not provide a value for `calendar_id`; let it use the default ('primary').
3. Present Slots & Ask Naturally:
    - If 'get_free_slots' returns a list of available slots (which are in precise YYYY-MM-DDTHH:MM:SSZ UTC format):
        - Present these slots clearly to the candidate. You can make them more readable (e.g., "April 5th, 9:00 AM - 5:00 PM UTC"). Crucially, always mention that the times are in UTC.
        - Ask the candidate to choose their preferred slot using natural language (e.g., "Which of these time slots works best for you?", "Please tell me the date and time you'd like from the options above.").
    - If 'get_free_slots' returns an empty list `[]` or an object containing an 'error' key:
        - Inform the candidate that no slots are available or that there was a problem checking the calendar (mention the error if provided in the response). Suggest trying again later or contacting support. Do not display the raw error object. Do not proceed to booking steps.
4. Understand & Match User Choice:
    - Parse the candidate's natural language response (e.g., "April 9th at 10 AM").
    - CRITICAL: Match the request to one of the available slots provided by `get_free_slots`. The slots are given in YYYY-MM-DDTHH:MM:SSZ format (e.g., '2025-04-09T09:00:00Z' to '2025-04-09T17:00:00Z'). Assume the year is 2025 for all user inputs since the slots are for 2025. Check if the user's requested date matches the slot's date, and if the requested time falls BETWEEN the slot's start and end times (e.g., for a slot from 9:00 AM to 5:00 PM UTC, any time like 3:00 PM should be accepted).
    - If the request doesn’t match any available slot (e.g., wrong date or time outside the slot range), ask for clarification with: "Sorry, that time doesn’t match any available slots. Please pick one from the list I provided."
5. Extract Exact Times & Get Email:
    - Once a slot is matched, ask the candidate to confirm the exact start and end time within the matched slot (e.g., for a slot from 9:00 AM to 5:00 PM, they might say "from 3:00 PM to 4:00 PM"). Ensure the start and end times they provide are within the slot's range.
    - Also, ask for their email address if not already provided (e.g., "Please provide your email address to book the slot.").
6. Book Interview:
    - Use the 'book_interview' tool.
    - Provide the exact `start_time` and `end_time` strings based on the user's confirmed times (e.g., '2025-04-09T15:00:00Z' to '2025-04-09T16:00:00Z'). Ensure the year is set to 2025 in the ISO format.
    - Provide the `candidate_email`.
    - Use the default `calendar_id` ('primary').
7. Confirm/Report Result:
    - Based on the response string from 'book_interview':
        - If it indicates success (e.g., starts with "Success!"), confirm the booking details (candidate email, date, start time, end time, mentioning TZ is UTC) to the candidate.
        - If it indicates failure (e.g., starts with "Failed"), inform the candidate about the failure and the reason provided. Suggest they choose a different slot if applicable.
8. Handle Off-Topic: Stick strictly to interview scheduling. Politely decline any off-topic requests.
''',
    tools=[get_free_slots, book_interview],
    model=model
)
# Chainlit UI Setup 
@cl.on_chat_start
async def start_chat():
    if not google_calendar_service:
        await cl.Message(content="Welcome! Unfortunately, I'm having trouble connecting to the calendar service right now. Please try again later or contact support.").send()
        cl.user_session.set("service_unavailable", True)
    else:
        cl.user_session.set("service_unavailable", False)
        cl.user_session.set("history", [])
        await cl.Message(content="Welcome to the Interview Scheduling Bot! I can help you find and book an interview slot. Would you like to see the available times?").send()

@cl.on_message
async def handle_message(message: cl.Message):
    history = cl.user_session.get("history")
    history.append({"role": "user", "content": message.content})

    msg = cl.Message(content="")
    await msg.send()

    result = Runner.run_streamed(agent, input=history, run_config=config)
    full_response = ""
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            await msg.stream_token(event.data.delta)
            full_response += event.data.delta

    history.append({"role": "assistant", "content": full_response})
    cl.user_session.set("history", history)
    await msg.update()

