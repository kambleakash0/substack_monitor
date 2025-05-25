# Substack Blog Summarizer & Notifier

A Python application that monitors a Substack blog for new posts, generates a summary of new articles using the Gemini API, and sends the summary to specified email addresses via Postmark. It includes a self-ping mechanism to stay active on hosting platforms like Render.

## Features

- **Substack Monitoring**: Regularly checks a specified Substack blog for new articles.
- **AI-Powered Summarization**: Uses Google's Gemini API to generate concise summaries of new posts.
- **Email Notifications**: Sends summaries to configured email addresses using Postmark.
- **Web Interface**: Provides a simple FastAPI interface to check status and control the worker.
- **Self-Pinging**: Includes a feature to periodically ping itself, preventing shutdown on free hosting tiers.
- **Easy Configuration**: Uses environment variables for all settings and API keys.
- **Containerization**: Includes a `Dockerfile` for easy deployment.

## How it Works

1.  The application starts and initializes a background worker and a self-ping service.
2.  The background worker periodically fetches the latest post from the configured Substack URL.
3.  If a new post is detected (i.e., its URL is different from the last processed post):
    a.  The content of the new post is extracted.
    b.  The extracted text is sent to the Gemini API for summarization.
    c.  The generated summary is then sent as an HTML email to the configured recipient(s) via Postmark.
    d.  The URL of the new post is saved as the last processed URL.
4.  The self-ping service sends a request to the application's `/health` endpoint at regular intervals to keep it alive on hosting platforms.
5.  API endpoints allow for checking the application status and manually starting/stopping the worker.

## Configuration

The application is configured via environment variables. Create a `.env` file in the root directory of the project or set these variables in your deployment environment:

-   `SUBSTACK_BLOG_URL`: **Required**. The full URL of the Substack blog to monitor (e.g., `https://yourblog.substack.com`).
-   `GEMINI_API_KEY`: **Required**. Your API key for the Google Gemini API.
-   `POSTMARK_API_TOKEN`: **Required**. Your server token for the Postmark email service.
-   `EMAIL_SENDER`: **Required**. The email address from which the summary emails will be sent (must be a registered sender in Postmark).
-   `EMAIL_RECEIVERS`: **Required**. A comma-separated list of email addresses to send the summaries to.
-   `CHECK_INTERVAL`: Optional. The interval in seconds at which to check for new posts. Defaults to `3600` (1 hour).
-   `SERVICE_URL`: Optional. The public URL of this service, used for self-pinging. Defaults to `http://localhost:8080` for local development. Ensure this is set to the correct public URL when deployed.
-   `PORT`: Optional. The port on which the FastAPI application will run. Defaults to `8080`.

## Setup and Running

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Create a `.env` file:**
    Copy the `.env.example` file (if one exists) or create a new file named `.env`. Populate it with your API keys and configuration details as described in the "Configuration" section.
    Example `.env` content:
    ```env
    SUBSTACK_BLOG_URL="https://yourblog.substack.com"
    GEMINI_API_KEY="your_gemini_api_key"
    POSTMARK_API_TOKEN="your_postmark_api_token"
    EMAIL_SENDER="sender@example.com"
    EMAIL_RECEIVERS="receiver1@example.com,receiver2@example.com"
    CHECK_INTERVAL="1800" # Check every 30 minutes
    SERVICE_URL="https://your-deployed-service-url.com" # Important for deployed environments
    PORT="8080"
    ```

3.  **Install dependencies:**
    It's recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --reload
    ```
    The `--reload` flag is useful for development and will automatically restart the server on code changes. The `${PORT:-8080}` syntax will use the PORT environment variable if set, otherwise default to 8080.

## API Endpoints

The application provides the following API endpoints:

-   `GET /`:
    -   Description: Returns the current status of the application, including whether the worker and ping service are active, and the URL of the last processed post.
    -   Response:
        ```json
        {
          "status": "running",
          "worker_active": true,
          "ping_active": true,
          "last_processed": "https://yourblog.substack.com/p/your-latest-post"
        }
        ```

-   `GET /health`:
    -   Description: A health check endpoint, primarily used by the self-ping service and for monitoring.
    -   Response:
        ```json
        {
          "status": "healthy",
          "timestamp": 1678886400.000
        }
        ```

-   `POST /start`:
    -   Description: Manually starts the background worker if it's not already running.
    -   Response:
        ```json
        {"status": "worker started"} 
        // or
        {"status": "worker already running"}
        ```

-   `POST /stop`:
    -   Description: Stops the background worker. The worker will finish its current cycle before stopping.
    -   Response:
        ```json
        {"status": "worker stopping - will finish current cycle"}
        // or
        {"status": "worker not running"}
        ```

## Deployment

This application is designed to be easily deployable.

### Docker

A `Dockerfile` is provided to build a container image for the application:

1.  **Build the Docker image:**
    ```bash
    docker build -t substack-summarizer .
    ```

2.  **Run the Docker container:**
    Make sure to pass the environment variables to the container. You can do this using a `.env` file with the `docker run --env-file .env ...` option or by passing each variable individually with the `-e` flag.
    ```bash
    docker run -d --env-file .env -p 8080:8080 substack-summarizer 
    ```
    (Ensure the `PORT` environment variable in your `.env` file or passed to the container matches the internal port, which is 8080 by default unless you change it in `app.py` or via the `PORT` env var itself).

### Render / PaaS

-   Connect your Git repository to Render (or a similar PaaS).
-   Specify the run command, which might be `uvicorn app:app --host 0.0.0.0 --port $PORT`. Many platforms set the `PORT` environment variable automatically.
-   Add all the required environment variables (as listed in the "Configuration" section) in the platform's dashboard. Ensure `SERVICE_URL` is set to the public URL provided by the platform.
-   The application uses `requirements.txt` to install dependencies.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
