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
