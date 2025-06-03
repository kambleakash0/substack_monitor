import os
import time
import requests
import threading
import google.generativeai as genai
import logging
import uvicorn
from fastapi import FastAPI

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from postmarker.core import PostmarkClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Substack Monitor Service")

# Load environment variables from .env file
load_dotenv()

# Configuration
SUBSTACK_URL = os.getenv("SUBSTACK_BLOG_URL")  # Your Substack URL
GOOGLE_AI_API_KEY = os.getenv("GEMINI_API_KEY")  # Get this from Google AI Studio
POSTMARK_SERVER_TOKEN = os.getenv("POSTMARK_API_TOKEN")  # Get this from SendGrid
SENDER_EMAIL = os.getenv("EMAIL_SENDER")  # Your email address
RECEIVER_EMAILS = os.getenv("EMAIL_RECEIVERS")  # Your email address
SLEEP_SECONDS = int(os.getenv("CHECK_INTERVAL", "3600"))  # Default to 1 hour if not specified
PING_INTERVAL = 600  # Ping every 10 minutes to prevent idle shutdown

# Configure Gemini
genai.configure(api_key=GOOGLE_AI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-lite-001')

# Global vars
last_processed = ""
worker_active = False
worker_thread = None
ping_active = False
ping_thread = None
# Get the service URL from environment, or default to localhost for development
SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080")

def get_last_processed_url():
    """Reads the last processed URL from the global variable."""
    global last_processed
    return last_processed

def save_last_processed_url(url):
    """Saves the last processed URL to the global variable."""
    global last_processed
    last_processed = url

def get_latest_substack_post_url(substack_url):
    """Fetches the Substack homepage and extracts the URL of the latest post."""
    try:
        response = requests.get(substack_url)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Adjust this selector according to your specific substack website structure
        first_post_link = soup.find("a", class_="sitemap-link") 
        if not first_post_link:
            logger.error("Could not find a post link with class name 'sitemap-link'. Check your substack URL and selectors")
            return None
        post_url = first_post_link['href'] 
        return post_url

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Substack homepage: {e}")
        return None

def extract_text_from_url(url):
    """Fetches the content of a URL and extracts the main text."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        content_div = soup.find("div", class_="body") 
        if not content_div:
            logger.error("Could not find the main content div with class name 'body'. Check your substack URL and selectors")
            return None
        paragraphs = content_div.find_all("p") 
        text = "\n".join(p.get_text() for p in paragraphs)
        return text

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching or parsing the URL: {e}")
        return None

def summarize_text(text, api_key):
    """Summarizes the text using Google's Gemini API."""
    try:
        prompt = f"Summarize the following text and \
            format it to be sent as HtmlBody parameter in a email API. \
                Don't add triple backticks to denote the block of text. \
                simply the HTML without even HEAD or BODY tags.\
                \n{text}\n\nSummary:"
        response = model.generate_content(prompt)

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            logger.error(f"The prompt was blocked because of: {response.prompt_feedback.block_reason}")
            return None # Handle the blocked prompt appropriately

        return response.text.strip()

    except Exception as e:
        logger.error(f"Error during Gemini summarization: {e}")
        return None

def send_simple_message(subject, body, sender_email, receiver_email, postmark_server_token):
    try:
        postmark = PostmarkClient(server_token=postmark_server_token)
        
        result = postmark.emails.send(
            From=sender_email,
            To=receiver_email,
            Subject=subject,
            HtmlBody="<p>" + body.replace("\n", "</p><p>") + "</p>",
        )
        logger.info(f"Email sent successfully: {result}")
        return result
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return None

def worker_process():
    """Main function to orchestrate the process."""
    global worker_active
    last_processed_url = get_last_processed_url()
    
    logger.info("Background worker started")
    
    while worker_active:
        try:
            logger.info(f"Checking for new posts at {SUBSTACK_URL}")
            latest_post_url = get_latest_substack_post_url(SUBSTACK_URL)

            if not latest_post_url:
                logger.warning("Failed to retrieve latest post URL. Retrying...")
                time.sleep(SLEEP_SECONDS)
                continue

            if latest_post_url != last_processed_url:
                logger.info(f"New post found: {latest_post_url}")
                text = extract_text_from_url(latest_post_url)

                if not text:
                    logger.warning("Failed to extract text. Retrying...")
                    time.sleep(SLEEP_SECONDS)
                    continue

                logger.info("Generating summary with Gemini")
                summary = summarize_text(text, GOOGLE_AI_API_KEY)

                if not summary:
                    logger.warning("Failed to summarize text. Retrying...")
                    time.sleep(SLEEP_SECONDS)
                    continue

                logger.info(f"Sending email summary of {latest_post_url}")
                
                send_simple_message(
                    subject="Summary of the latest EAS503 Substack post",
                    body=f"Summary of {latest_post_url}:\n\n{summary}",
                    sender_email=SENDER_EMAIL,
                    receiver_email=RECEIVER_EMAILS,
                    postmark_server_token=POSTMARK_SERVER_TOKEN,
                )

                save_last_processed_url(latest_post_url)
                last_processed_url = latest_post_url 

            else:
                logger.info("No new posts found.")

            logger.info(f"Sleeping for {SLEEP_SECONDS} seconds")
            time.sleep(SLEEP_SECONDS)
            
        except Exception as e:
            logger.error(f"Error in worker process: {e}")
            time.sleep(SLEEP_SECONDS)  # Sleep and continue even if there's an error

def self_ping():
    """Ping itself regularly to prevent Render from shutting down due to inactivity."""
    global ping_active
    
    logger.info(f"Self-ping service started, will ping {SERVICE_URL}/health every {PING_INTERVAL} seconds")
    
    while ping_active:
        try:
            response = requests.get(f"{SERVICE_URL}/health")
            logger.info(f"Self-ping: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error during self-ping: {e}")
        
        time.sleep(PING_INTERVAL)

# FastAPI routes
@app.get("/")
def index():
    return {
        "status": "running",
        "worker_active": worker_active,
        "ping_active": ping_active,
        "last_processed": last_processed or "None"
    }

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": time.time()}

@app.post("/start")
def start_worker():
    global worker_active, worker_thread
    
    if not worker_active:
        worker_active = True
        worker_thread = threading.Thread(target=worker_process)
        worker_thread.daemon = True  # This makes the thread exit when the main program exits
        worker_thread.start()
        return {"status": "worker started"}
    else:
        return {"status": "worker already running"}

@app.post("/stop")
def stop_worker():
    global worker_active
    
    if worker_active:
        worker_active = False
        return {"status": "worker stopping - will finish current cycle"}
    else:
        return {"status": "worker not running"}

# Startup event
@app.on_event("startup")
def on_startup():
    global worker_active, worker_thread, ping_active, ping_thread
    # Start the background worker
    worker_active = True
    worker_thread = threading.Thread(target=worker_process)
    worker_thread.daemon = True
    worker_thread.start()
    
    # Start the self-ping service
    ping_active = True
    ping_thread = threading.Thread(target=self_ping)
    ping_thread.daemon = True
    ping_thread.start()
    
    logger.info("FastAPI application started with background worker and self-ping service")

# Shutdown event
@app.on_event("shutdown")
def on_shutdown():
    global worker_active, ping_active
    worker_active = False
    ping_active = False
    logger.info("FastAPI application shutting down, worker and ping service stopping")

if __name__ == "__main__":
    # Get the port from environment variable for Render compatibility
    port = int(os.environ.get("PORT", 8080))
    
    # Start the FastAPI app with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")