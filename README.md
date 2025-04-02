# Interview Scheduling Bot

This Python bot automates the process of scheduling interviews using the Google Calendar API. It allows you to find free time slots in a specified calendar and book interview appointments with candidates.

## Key Features

* **Fetches Free Slots:** Identifies available time slots in your Google Calendar for the upcoming 14 days (by default), considering working hours between 9 AM and 5 PM UTC.
* **Books Interviews:** Schedules interview events in your Google Calendar for a selected time slot and candidate email.
* **Email Notifications:** Sends automated email invitations to both the candidate and the recruiter upon successful booking.
* **Chainlit Integration:** Provides an interactive user interface using Chainlit for easy scheduling.

## Prerequisites

Before running the bot, ensure you have the following:

* **Python 3.6 or higher:** Make sure you have Python installed on your system.
* **Google Cloud Project:** You need a Google Cloud Project with the Google Calendar API enabled.
* **Google Calendar API Credentials:** You'll need to create and download the `credentials.json` file for your Google Cloud Project.
* **Chainlit:** Install Chainlit to run the interactive interface.
* **python-dotenv:** Install python-dotenv to manage environment variables.

## Installation

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Install required Python packages:**
    ```bash
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib chainlit python-dotenv
    ```

3.  **Set up Google Cloud Project and API Credentials:**
    * Go to the [Google Cloud Console](https://console.cloud.google.com/).
    * Create or select an existing project.
    * Enable the **Google Calendar API**.
    * Create **OAuth 2.0 credentials** for a **Desktop application**.
    * Download the generated **`credentials.json`** file and place it in the same directory as your Python script (`bot.py`).

4.  **Set up Environment Variables:**
    * Create a `.env` file in the same directory as your script.
    * Add the following environment variable, replacing `<your_email@example.com>` with the recruiter's email address:
        ```env
        RECRUITER_EMAIL=<your_email@example.com>
        ```

## Usage

1.  **Run the Chainlit application:**
    ```bash
    chainlit run bot.py -w
    ```
    This command will start the Chainlit interface in your web browser (usually at `http://localhost:8000`).

2.  **Interact with the bot:** Follow the instructions in the Chainlit interface to schedule an interview. You will likely be prompted to:
    * Provide the candidate's email address.
    * View available time slots fetched from your Google Calendar.
    * Select a suitable time slot to book the interview.

3.  **Google Calendar Permission:** The first time you run the script, it will likely open a web browser window asking you to authorize the application to access your Google Calendar. Make sure to grant the necessary permissions.

## Configuration

You can configure the following variables in your `bot.py` file:

* `DEFAULT_CALENDAR_ID`: This is set to `'primary'` by default, which refers to your primary Google Calendar. You can change this to the ID of a different calendar if needed.
* `RECRUITER_EMAIL`: This is loaded from the `.env` file and used to include the recruiter in the interview invitation.

## Troubleshooting

* **Google Permission Page Not Showing:**
    * Delete the `token.pickle` file in the same directory as your script. This file stores your authentication tokens. Deleting it will force the script to ask for permission again when you run it.
    * Ensure your `credentials.json` file is correctly placed in the same directory.
* **Events Not Appearing in Calendar:**
    * Double-check the date and time of the booked event in your local timezone. The bot uses UTC for calculations and stores the event in UTC.
    * Verify that you have granted the necessary permissions to the bot to write to your calendar.
    * Check the console output for any error messages during the booking process.
* **Incorrect Year for Bookings:**
    * Ensure that the `get_free_slots` function in your `bot.py` file is using the current year when determining free slots. Refer to the conversation history for the correct code modification.
    * Make sure you have saved the changes to your `bot.py` file and restarted the Chainlit application.

