# Online Database Viewer

## Introduction

The Online Database Viewer is a web-based application designed to allow users to easily upload, view, and explore the contents of various database files directly in their browser. No complex setup or local software installation is required to inspect your data. This tool is particularly useful for quick data checks, schema exploration, and simple data retrieval tasks.

Built with Python, Flask, and a touch of JavaScript, it aims to provide a user-friendly interface for interacting with your databases.

## Features

*   **Web-Based Interface**: Access your databases from any modern web browser.
*   **File Upload**: Securely upload your database files.
*   **Table Browsing**: List and view tables within your uploaded database.
*   **Data Viewing**: Paginated view of table data.
*   **Search Functionality**: Search data within tables.
*   **Sorting**: Sort table data by columns.
*   **Responsive Design**: Usable on different screen sizes.
*   **Admin Operations**:
    *   Delete individual databases.
    *   Cleanup all uploaded databases (requires admin token).
*   **CSRF Protection**: Enhanced security for form submissions.

## Supported Databases

Currently, the application supports the following database formats:

*   **Microsoft Access**: `.mdb`, `.accdb`
*   **SQLite**: `.sqlite`, `.db`

*Note: While SQLite file upload and basic table/data viewing are enabled, full functionality for SQLite (like complex column information and robust searching of all identifier types) is still under development and may have limitations.*

## Setup and Installation

The application is designed to be run as a standard Flask application.

1.  **Clone the repository (if applicable):**
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Install Dependencies:**
    It's recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    pip install -r requirements.txt 
    ```
    *(Note: A `requirements.txt` file would typically list Flask, pyodbc, Flask-WTF, python-dotenv. If not present, these would need to be installed manually: `pip install Flask pyodbc Flask-WTF python-dotenv`)*

3.  **Environment Variables:**
    Create a `.env` file in the root directory of the project and configure the following variables:
    *   `FLASK_SECRET_KEY`: A strong, random string used for session security and CSRF protection. If not set in production, the application will not run. For development, a default insecure key is used if `FLASK_DEBUG=1`.
        ```
        FLASK_SECRET_KEY='your_super_secret_random_key_here'
        ```
    *   `DBVIEWER_ADMIN_TOKEN` (Optional but Recommended): A token for authorizing destructive operations like deleting databases. If not set, these operations are disabled unless in debug mode (where a default insecure token "admin-debug-token" is used).
        ```
        DBVIEWER_ADMIN_TOKEN='your_secure_admin_token'
        ```

## Usage

1.  **Run the Application:**
    ```bash
    python dbviewer.py
    ```
    By default, the application will be available at `http://127.0.0.1:5000/`. If `debug=True` is set in `app.run()`, it might run on `0.0.0.0` making it accessible on your local network.

2.  **Open in Browser:**
    Navigate to `http://127.0.0.1:5000/` in your web browser.

3.  **Upload a Database:**
    *   Drag and drop your database file (`.mdb`, `.accdb`, `.sqlite`, `.db`) onto the upload area.
    *   Or, click the "Choose Database File" button to select a file using your system's file dialog.
    *   Maximum file size is 100MB.

4.  **Explore Data:**
    *   Once uploaded, the database will appear in the "Your Databases" list.
    *   Select a database to see its tables.
    *   Click on a table name to view its data.
    *   Use the search bar, sort options, and pagination to navigate the data.

5.  **Admin Actions (Deleting Databases):**
    *   To delete a database, select it, and the "Delete Database" button will appear.
    *   To use this feature (or "Cleanup All"), you must have `DBVIEWER_ADMIN_TOKEN` configured on the server. When prompted (or if using API tools), provide this token, typically as an `X-Admin-Token` header for API calls if a UI prompt isn't available for a specific action. The application currently does not have a UI input for the admin token for these actions directly in the browser, relying on the server-side check. *Future enhancement could include a UI prompt for the token.*

## Screenshots

*(Placeholder for screenshots - e.g., main upload page, table view, search results)*

*   `screenshot_main_page.png`: Shows the initial landing page and upload area.
*   `screenshot_table_view.png`: Illustrates how data is displayed within a table.

## Contributing

*(Placeholder for contribution guidelines)*

We welcome contributions! Please follow these steps:
1.  Fork the repository.
2.  Create a new branch (`git checkout -b feature/AmazingFeature`).
3.  Make your changes.
4.  Commit your changes (`git commit -m 'Add some AmazingFeature'`).
5.  Push to the branch (`git push origin feature/AmazingFeature`).
6.  Open a Pull Request.

Please make sure to update tests as appropriate.

## License

*(Placeholder for license information)*

Distributed under the MIT License. See `LICENSE.txt` for more information.
(Assuming MIT License, adjust if different. A `LICENSE.txt` file would need to be created.)

---

Thank you for using the Online Database Viewer!

---

## Running with Docker (Production Ready)

This application is configured to run with Docker and Docker Compose, including Nginx as a reverse proxy and Redis for rate limiting and potential future caching/session management.

### Prerequisites

*   Docker: [Install Docker](https://docs.docker.com/get-docker/)
*   Docker Compose: [Install Docker Compose](https://docs.docker.com/compose/install/) (often included with Docker Desktop)

### Configuration

1.  **Create a `.env` file:**
    In the root directory of the project, create a `.env` file. This file will store your secret configurations.
    ```env
    # .env file
    FLASK_SECRET_KEY='your_very_strong_random_flask_secret_key_here'
    DBVIEWER_ADMIN_TOKEN='your_secure_admin_token_for_delete_operations'

    # Optional: If you want to change the default port Gunicorn runs on inside the container
    # FLASK_RUN_PORT=5000 
    ```
    *   `FLASK_SECRET_KEY`: **Required for production.** A long, random, and unique string. You can generate one using `python -c 'import secrets; print(secrets.token_hex(32))'`.
    *   `DBVIEWER_ADMIN_TOKEN`: **Required for admin operations** (deleting databases). Choose a strong, unique token.

### Building and Running

1.  **Open your terminal** in the project's root directory (where `docker-compose.yml` is located).

2.  **Build and run the services in detached mode:**
    ```bash
    docker-compose up --build -d
    ```
    *   `--build`: Forces Docker Compose to rebuild the images if they don't exist or if the Dockerfiles/code have changed.
    *   `-d`: Runs the containers in detached mode (in the background).

3.  **Accessing the application:**
    Once the containers are up and running, the application will be accessible at:
    `http://localhost/` (or `http://<your-server-ip>/` if deployed on a server). Nginx listens on port 80.

### Managing Services

*   **To view logs:**
    ```bash
    docker-compose logs -f            # View logs for all services
    docker-compose logs -f app        # View logs for the Flask app service
    docker-compose logs -f nginx      # View logs for the Nginx service
    docker-compose logs -f redis      # View logs for the Redis service
    ```

*   **To stop the services:**
    ```bash
    docker-compose down
    ```
    This command stops and removes the containers, networks, and (by default) named volumes unless specified otherwise. If you want to preserve named volumes (like `redis_data`), they won't be removed by default.

*   **To stop and remove volumes (including persistent data like Redis cache and uploads):**
    ```bash
    docker-compose down -v
    ```
    **Caution:** This will delete any uploaded database files and Redis data stored in Docker volumes.

### Volumes

*   `redis_data`: Persists Redis data across container restarts.
*   `./uploads` (bind mount): Persists uploaded database files on your host machine in the `uploads/` directory.
*   `./app.log` (bind mount): Persists the application log file on your host machine as `app.log`.

### Further Production Considerations

*   **HTTPS:** The provided Nginx configuration is for HTTP. For production, you should configure HTTPS using SSL/TLS certificates (e.g., with Let's Encrypt). This involves updating `nginx.conf` and potentially the `docker-compose.yml` for certificate management.
*   **Database Backups (for `uploads/`):** Ensure you have a backup strategy for the `uploads/` directory if the data is critical.
*   **Resource Allocation:** Adjust Gunicorn worker counts (`--workers` in the app's Dockerfile `CMD`) and Nginx worker processes based on your server's resources and expected load.
*   **Security Hardening:** Review security best practices for Docker, Nginx, and Flask applications.
*   **ODBC Drivers for MS Access on Linux:** The Flask app's `Dockerfile` includes `unixodbc-dev`. For full MS Access (`.mdb`/`.accdb`) functionality on a Linux Docker host, you might need to install specific ODBC drivers like `mdbtools` and `libmdbodbc1` (e.g., `apt-get install -y mdbtools libmdbodbc1`). Test thoroughly if this is a primary use case. SQLite is generally more straightforward in a Linux Docker environment.
