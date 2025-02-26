import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()



# Configuration
SUBSTACK_URL = os.getenv("SUBSTACK_BLOG_URL")  # Your Substack URL
GOOGLE_AI_API_KEY = os.getenv("GEMINI_API_KEY")  # Get this from Google AI Studio
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")  # Get this from SendGrid
SENDER_EMAIL = os.getenv("EMAIL_SENDER")  # Your email address
RECEIVER_EMAILS = os.getenv("EMAIL_RECEIVERS")  # Your email address
STATE_FILE = "last_processed.txt"  # File to store the last processed URL
SLEEP_SECONDS = int(os.getenv("CHECK_INTERVAL")) # Check every 60 minutes

# Configure Gemini
genai.configure(api_key=GOOGLE_AI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro-latest')

# model = genai.GenerativeModel('gemini-pro')  
# Or 'gemini-pro-vision' if you need image support

def get_last_processed_url():
    """Reads the last processed URL from the state file."""
    try:
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

def save_last_processed_url(url):
    """Saves the last processed URL to the state file."""
    with open(STATE_FILE, "w") as f:
        f.write(url)

def get_latest_substack_post_url(substack_url):
    """Fetches the Substack homepage and extracts the URL of the latest post."""
    try:
        response = requests.get(substack_url)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Adjust this selector according to your specific substack website structure
        # Find the first link that appears to be a blog post link
        first_post_link = soup.find("a", class_="sitemap-link") #This is a common selector class name
        if not first_post_link:
            print("Could not find a post link with class name 'post-link'. Check your substack URL and selectors")
            return None
        post_url = first_post_link['href'] # Assuming relative URL
        return post_url

    except requests.exceptions.RequestException as e:
        print(f"Error fetching Substack homepage: {e}")
        return None

def extract_text_from_url(url):
    """Fetches the content of a URL and extracts the main text."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        #Adjust this selector according to your specific substack website structure
        # Find the main content area (you'll need to inspect the Substack page)
        content_div = soup.find("div", class_="body") #Or use another appropriate tag/class
        if not content_div:
            print("Could not find the main content div with class name 'body'. Check your substack URL and selectors")
            return None
        paragraphs = content_div.find_all("p") #Or whatever tag contains the main content
        text = "\n".join(p.get_text() for p in paragraphs)
        return text

    except requests.exceptions.RequestException as e:
        print(f"Error fetching or parsing the URL: {e}")
        return None

def summarize_text(text, api_key):
    """Summarizes the text using Google's Gemini API."""
    try:
        
        prompt = f"Summarize the following text:\n{text}\n\nSummary:"
        response = model.generate_content(prompt)

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            print(f"The prompt was blocked because of: {response.prompt_feedback.block_reason}")
            return None # Handle the blocked prompt appropriately

        return response.text.strip()

    except Exception as e:
        print(f"Error during Gemini summarization: {e}")
        return None

def send_email(subject, body, sender_email, receiver_email, sendgrid_api_key):
    """Sends an email using Twilio SendGrid API."""
    message = Mail(
        from_email=sender_email,
        to_emails=receiver_email,
        subject=subject,
        html_content=body
    )

    try:
        sg = SendGridAPIClient(os.environ.get(sendgrid_api_key))
        response = sg.send(message)

        if response.status_code == 202:
            print("Email sent successfully via SendGrid!")
        else:
            print(f"Error sending email via SendGrid. Status code: {response.status_code}, Body: {response.body}, Headers: {response.headers}")
    except Exception as e:
        print(f"Error sending email via SendGrid: {e}")

def main():
    """Main function to orchestrate the process."""
    last_processed_url = get_last_processed_url()
    # print(genai.list_models())
    while True:
        latest_post_url = get_latest_substack_post_url(SUBSTACK_URL)

        if not latest_post_url:
            print("Failed to retrieve latest post URL. Retrying...")
            time.sleep(SLEEP_SECONDS)
            continue

        if latest_post_url != last_processed_url:
            print(f"New post found: {latest_post_url}")
            text = extract_text_from_url(latest_post_url)

            if not text:
                print("Failed to extract text. Retrying...")
                time.sleep(SLEEP_SECONDS)
                continue

            summary = summarize_text(text, GOOGLE_AI_API_KEY)

            if not summary:
                print("Failed to summarize text. Retrying...")
                time.sleep(SLEEP_SECONDS)
                continue

            print(f"Summary of {latest_post_url}:\n\n{summary}")
            # send_email(
            #     subject="Summary of the latest EAS503 Substack post",
            #     body=f"Summary of {latest_post_url}:\n\n{summary}",
            #     sender_email=SENDER_EMAIL,
            #     receiver_email=RECEIVER_EMAILS,
            #     sendgrid_api_key=SENDGRID_API_KEY,
            # )

            # save_last_processed_url(latest_post_url)
            # last_processed_url = latest_post_url #Update in memory

        else:
            print("No new posts found.")

        time.sleep(SLEEP_SECONDS)  # Check every SLEEP_SECONDS seconds


if __name__ == "__main__":
    main()