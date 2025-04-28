# GitHub Ops Manager (`github-ops-manager`)

## Overview and Overarching Goal

This project aims to create a flexible and robust Python tool, `github-ops-manager`, designed to automate common GitHub workflows based on declarative configuration files, primarily YAML. It stems from internal tooling but is intended to be a standalone, reusable tool for broader use cases on both GitHub.com and GitHub Enterprise Server (GHES).

The **overarching goal** is to provide a modular and configurable command-line interface (CLI) application that can:

1. **Read structured data** (initially from YAML files) describing desired states or actions in a GitHub repository.
2. **Interact with the GitHub API** to enact those states/actions, authenticating either via a **GitHub App (recommended)** or a **Personal Access Token (PAT)**.
3. **(Forward Sync)**: Synchronize YAML definitions to GitHub issues (create or update).
4. **(Reverse Sync / Import)**: Optionally, read existing GitHub issues from a repository and export them to a structured YAML file format compatible with this tool.
5. **Extensible functionality:** Optionally handle associated artifacts (like generated code files), commit them to unique branches, and create corresponding Pull Requests linked to the issues.
6. **Be highly configurable and flexible**, especially regarding the structure of the input YAML files, allowing different teams or projects to adapt it to their needs.
7. **Be decoupled** from any specific application logic (like the original Quicksilver tool), focusing solely on GitHub operations driven by configuration.

This README serves as a guide for the development of this tool, targeting a developer implementing the core features.

## High-Level Requirements

The `github-ops-manager` tool must fulfill the following core requirements:

1. **Configuration & Authentication:**
    * Load GitHub connection details securely, prioritizing GitHub App credentials over Personal Access Tokens (PATs).
    * **Supported Authentication Methods:**
        * **GitHub App (Preferred):**
            * GitHub App ID (e.g., `GITHUB_APP_ID` env var).
            * GitHub App Private Key (e.g., path via `GITHUB_PRIVATE_KEY_PATH` env var or the key content itself via `GITHUB_PRIVATE_KEY` env var).
            * GitHub App Installation ID (e.g., `GITHUB_INSTALLATION_ID` env var - specifies which installation to act as). The tool should ideally include logic to find the installation ID for a target repo/org if not provided directly.
        * **Personal Access Token (Fallback):**
            * GitHub PAT (e.g., `GITHUB_TOKEN` env var).
    * Target GitHub Base URL (e.g., `GITHUB_BASE_URL` env var). Defaults to `https://api.github.com`. Crucial for GHES.
    * Target Repository URL or `owner/repo` slug (specified via CLI argument).
    * The tool must detect which set of credentials are provided (checking for App credentials first) and initialize the GitHub client (`githubkit`) accordingly. If neither is configured, provide a clear error.
    * Allow configuration of tool behavior (e.g., default branch, YAML parsing strategies) potentially via a config file (`pyproject.toml` or dedicated file).

    **1.A. GitHub App Configuration (If using App Auth):**
    * The GitHub App used by the tool must be registered on GitHub (or the target GHES instance).
    * It needs to be configured with the appropriate **permissions**. Likely required permissions:
        * **Repository Permissions:** `Contents: Read & Write`, `Issues: Read & Write`, `Metadata: Read-only`, `Pull requests: Read & Write`, `Administration: Read-only` (check if needed).
        * **Organization Permissions:** `Members: Read-only` (potentially).
    * *Note:* Select the minimum required permissions for security.

    **1.B. GitHub App Installation (If using App Auth):**
    * The GitHub App must be *installed* on the target organization or specific repositories where the `github-ops-manager` tool needs to operate.

2. **Input Processing (YAML Focus):**
    * Accept one or more paths to input YAML files via CLI arguments.
    * Robustly parse the YAML files. Handle potential syntax errors gracefully using `PyYAML` or `ruamel.yaml`.
    * **Flexibility:** Design the parser to accommodate variations in YAML structure.
        * Define a default expected schema for issues (e.g., a list under an `issues:` key, with each item having `title`, `body`, `labels`, etc.). Use Pydantic models internally for validation *after* mapping.
        * Provide a mechanism (e.g., configuration file section, CLI arguments) for users to map *their* YAML fields to the tool's internal representation if their structure differs significantly (e.g., `my_issue_title -> title`, `tags -> labels`).
        * Document the default expected schema(s) clearly in the tool's documentation or `--help` output.

3. **GitHub Issue Management (Forward Sync: YAML -> GitHub):**
    * Authenticate and connect to the target GitHub repository using the configured method (App or PAT) via `githubkit`.
    * Iterate through the items parsed from the input YAML(s).
    * For each item representing an issue:
        * Check if an issue with a matching identifier (e.g., the `title`) already exists.
        * **Create:** If no matching issue exists, create a new GitHub issue using details mapped from the YAML (e.g., `title`, `body`, `labels`, `assignees`, `milestone`).
        * **Update:** If a matching issue *does* exist (and update functionality is enabled via CLI flag), update its attributes (e.g., body, labels, assignees, milestone, state) to match the YAML definition.
        * Render the issue body content. Support simple templating if the YAML provides a template path or inline template string.
        * Log actions clearly (e.g., "Created issue #123 using App Auth", "Updated labels for issue #45 using PAT Auth").

4. **GitHub File & PR Management (Extension):**
    * Optionally (e.g., triggered by a CLI flag `--create-prs` and corresponding YAML data), handle file artifacts associated with an issue item.
    * For each item with associated files:
        * Create a unique, descriptively named branch originating from the repository's default branch (e.g., `feature/123-issue-title-slug`).
        * Commit the specified file(s) with provided content to this new branch.
        * Create a Pull Request targeting the repository's default branch.
        * The PR title/body must reference and link to the corresponding GitHub issue (e.g., "Closes #123").
        * Apply relevant labels to the PR.
        * Log actions clearly.

5. **GitHub Issue Export (Reverse Sync: GitHub -> YAML):**
    * **(New Requirement):** Provide functionality to read existing issues from a target repository and export them into a structured YAML file.
    * **Input:** Target repository, optional filters (e.g., `--label "bug"`, `--state "open"`, `--since "YYYY-MM-DD"`).
    * **Process:**
        * Fetch issues from the target repository using specified filters via `githubkit`.
        * For each fetched issue, extract key fields: `number`, `title`, `body` (as raw markdown), `labels` (as a list of names), `assignees` (list of logins), `milestone` (title), `state`, `created_at`, `updated_at`. Consider optionally including comments.
        * Structure the extracted data for each issue in a format consistent with the tool's expected *input* YAML schema (Requirement #2).
    * **Output:** Generate a YAML file (path specified via CLI, e.g., `--output-file exported_issues.yaml`) containing the list of structured issue data.

6. **Modularity & Design:**
    * Structure the codebase logically into distinct modules (e.g., `cli`, `config`, `auth`, `github` interactions, `processing`, `schemas`).
    * Employ object-oriented principles where appropriate.
    * Prioritize clear, readable, and maintainable "Pythonic" code with extensive type hinting.

7. **Error Handling & Resilience:**
    * Implement robust error handling for API errors (auth failures, rate limits, not found, validation errors), file system errors, YAML parsing errors, and configuration errors.
    * Provide informative error messages indicating the context (e.g., which auth method was used, which YAML file/item failed).
    * Leverage `githubkit`'s error handling and implement appropriate retry logic, especially for rate limits.

8. **Command-Line Interface (CLI):**
    * Develop a user-friendly CLI using `Typer` or `Click`.
    * Required arguments: Input YAML file path(s), target repository (`owner/repo`).
    * Optional arguments/flags: `--create-prs`, `--update-existing`, `--config-file`, potentially arguments for YAML field mapping overrides, `--verbose`/`--quiet`.
    * The CLI should clearly indicate which authentication method is being used based on detected credentials.

9. **Testing:**
    * Implement comprehensive unit tests covering different logic paths, including both App and PAT authentication flows (using mocking).
    * Implement integration tests against a mock GitHub API or a dedicated test repository.

10. **Documentation:**
    * Maintain this `README.md` with clear instructions for both authentication methods, configuration details, GHES usage, and examples.
    * Include docstrings for public modules, classes, and functions.
    * Provide example YAML input files and example configuration snippets.

## Suggested Core Libraries

* **GitHub Interaction:** [`githubkit`](https://github.com/yanyongyu/githubkit) - Modern, typed, supports both GitHub App and PAT authentication.
* **CLI Framework:** [`Typer`](https://typer.tiangolo.com/) or [`Click`](https://click.palletsprojects.com/) - For building the command-line interface.
* **YAML Parsing:** [`PyYAML`](https://pyyaml.org/) or [`ruamel.yaml`](https://yaml.readthedocs.io/en/latest/) - `ruamel.yaml` is preferred if comment/order preservation is needed.
* **Data Validation/Schemas:** [`Pydantic`](https://docs.pydantic.dev/) - For configuration and internal data model validation.
* **Environment/Package Mgmt:** [`uv`](https://github.com/astral-sh/uv) - For environment and dependency management.
* **Environment Variables (Optional):** [`python-dotenv`](https://pypi.org/project/python-dotenv/) - Useful for loading credentials from a `.env` file during local development.

## Suggested Project Structure

A proposed structure focusing on modularity:

```bash
github-ops-manager/
├── .github/
│   └── workflows/
│       └── ci.yml         # Linting, testing, build pipeline
├── .venv/                  # Virtual environment (created by uv)
├── config_examples/
│   └── issues_default.yaml # Example YAML for the default issue schema
│   └── config.toml         # Example tool configuration (optional)
├── github_ops_manager/     # Main Python package source
│   ├── __init__.py
│   ├── auth.py             # Logic to detect/handle App vs PAT auth
│   ├── cli.py              # CLI definition (Typer/Click app) - Add 'export-issues' command here
│   ├── config.py           # Loading config (URLs, settings - reads auth from env/dotenv)
│   ├── github/             # Module for GitHub API interactions via githubkit
│   │   ├── __init__.py
│   │   ├── client.py       # Authenticated githubkit client setup (accepts auth object)
│   │   ├── issues.py       # Functions for creating/updating/fetching issues - Add 'get_issues' here
│   │   ├── pull_requests.py # Functions for creating/updating PRs
│   │   ├── repositories.py # Functions for repo info, branches, commits, files
│   │   └── models.py       # Pydantic models for GitHub data (if needed beyond githubkit)
│   ├── processing/         # Core workflow logic
│   │   ├── __init__.py
│   │   ├── yaml_processor.py # Reads/maps YAML input, writes YAML output
│   │   ├── workflow_runner.py # Orchestrates actions (sync-to-github, export-issues)
│   │   └── models.py       # Internal data models (e.g., processed issue data)
│   ├── schemas/            # Pydantic models for input validation
│   │   ├── __init__.py
│   │   └── default_issue.py # Schema for the default expected YAML issue structure
│   └── utils.py            # Common helper functions (logging setup, etc.)
├── tests/                  # Unit and integration tests
│   ├── __init__.py
│   ├── fixtures/           # Test data, mock responses
│   ├── unit/
│   └── integration/
├── .env.example            # Example environment variables file
├── .gitignore
├── LICENSE                 # Choose an appropriate open-source license (e.g., MIT, Apache 2.0)
├── pyproject.toml          # Project metadata, dependencies, tool config (ruff, pytest, uv)
├── README.md               # This file
└── pre-commit-config.yaml  # Configuration for pre-commit hooks
```

## Setup & Local Development Environment

This project uses [`uv`](https://github.com/astral-sh/uv) for environment and package management, and `pre-commit` for code quality checks.

1. **Clone the Repository:**
    *(Note: Update the URL once the repository is created)*

    ```bash
    # Example placeholder URL - replace with actual repo URL
    git clone <your-repository-url>
    cd github-ops-manager/
    ```

2. **Prerequisites:**
    * Python 3.9+ (Check `pyproject.toml` for the specific minimum version)
    * `uv` installed (`pip install uv` or follow official instructions)
    * `pre-commit` installed (`pip install pre-commit`)

3. **Create and Activate Virtual Environment using `uv`:**

    ```bash
    # Create a virtual environment named .venv in the project root
    uv venv

    # Activate the environment
    # Linux/macOS:
    source .venv/bin/activate
    # Windows (Command Prompt):
    # .venv\Scripts\activate.bat
    # Windows (PowerShell):
    # .venv\Scripts\Activate.ps1
    ```

4. **Install Dependencies using `uv`:**
    Dependencies are defined in `pyproject.toml`.

    ```bash
    # Install main dependencies and development dependencies ([dev])
    # The -e flag installs the 'github-ops-manager' package itself in editable mode
    uv pip install -e ".[dev]"
    ```

5. **Set up Pre-commit Hooks:**
    Installs git hooks defined in `.pre-commit-config.yaml` to run linters/formatters automatically.

    ```bash
    pre-commit install
    ```

6. **Configure Authentication (Choose ONE method):**
    Set environment variables for authentication. Using a `.env` file (copy `.env.example` to `.env` and fill it out - ensure `.env` is in `.gitignore`!) is recommended for local development. The tool will prioritize GitHub App credentials if found.

    **Method 1: GitHub App (Recommended)**
    *Register a GitHub App and install it on your target repository/organization.*

    ```bash
    # In your .env file or shell environment:
    export GITHUB_APP_ID="<your_app_id>"
    # Provide the private key content directly or path to the .pem file
    # export GITHUB_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n..."
    export GITHUB_PRIVATE_KEY_PATH="/path/to/your-app.private-key.pem"
    export GITHUB_INSTALLATION_ID="<installation_id_for_target_repo_or_org>"
    # Optional: For GitHub Enterprise Server (GHES)
    # export GITHUB_BASE_URL="[https://your.github.enterprise.url/api/v3](https://your.github.enterprise.url/api/v3)"
    ```

    *Why preferred?* Better security (granular permissions, short-lived tokens), higher/scalable rate limits, no need for a bot user account.

    **Method 2: Personal Access Token (PAT) (Fallback)**
    *Create a PAT (classic or fine-grained) with necessary scopes (repo, issue, workflow, etc.).*

    ```bash
    # In your .env file or shell environment:
    export GITHUB_TOKEN="ghp_YourPersonalAccessTokenHere"
    # Optional: For GitHub Enterprise Server (GHES)
    # export GITHUB_BASE_URL="[https://your.github.enterprise.url/api/v3](https://your.github.enterprise.url/api/v3)"
    ```

    *Use Case:* Simpler setup, or when registering/installing a GitHub App on a target (especially GHES) is difficult or blocked by administrative process. Less secure than a GitHub App.

7. **Run the Tool (Example Usage - Conceptual):**
    *(Commands will be refined as the CLI (`cli.py`) is developed)*

    ```bash
    # Example: Process issues from a YAML file (auth detected automatically)
    github-ops-manager process-issues \
        --repo "owner/repository-name" \
        --yaml-path ./config_examples/issues_default.yaml

    # Example: Process issues AND create PRs for associated files
    github-ops-manager process-issues \
        --repo "owner/repository-name" \
        --yaml-path ./path/to/your_issues.yaml \
        --create-prs

    # Example: Export existing GitHub issues to YAML (GitHub -> YAML)
    github-ops-manager export-issues \
        --repo "owner/repository-name" \
        --output-file ./exported_issues.yaml \
        --state "open" \
        --label "bug"
    ```

8. **Run Tests:**
    Execute the test suite using `pytest`.

    ```bash
    pytest tests/
    ```

9. **Run Linters/Formatters Manually (Optional):**
    `pre-commit` handles this automatically on commit.

    ```bash
    # Example using Ruff (if configured)
    ruff check .
    ruff format .

    # Example using Mypy (if configured)
    mypy .
    ```

## GitHub Enterprise Server (GHES) Usage

This tool can be used with GitHub Enterprise Server instances, but requires specific considerations:

1. **Authentication:**
    * **GitHub App (Preferred):** The GitHub App must be registered *directly* on the target GHES instance by a GHES admin or Organization Owner (using a manifest file or setup URL provided by this project). Once registered and installed on your GHES org/repo, configure the tool using the GHES App ID, Private Key, Installation ID, and the `GITHUB_BASE_URL`.
    * **Personal Access Token (Fallback):** If registering/installing the GitHub App on your GHES instance is not feasible due to administrative hurdles, you can use a PAT generated on the GHES instance. Configure the tool using `GITHUB_TOKEN` and `GITHUB_BASE_URL`.

2. **App Registration on GHES (If using App Auth):** A GitHub App registered on public GitHub.com *cannot* be installed on a GHES instance. This project should provide mechanisms (e.g., a `manifest.yml` file in the repo) for GHES administrators to register the app on their instance.

3. **Configuration:** The `GITHUB_BASE_URL` environment variable (or equivalent configuration) *must* be set to the GHES instance's API endpoint (e.g., `https://your.ghe.domain/api/v3`) regardless of the authentication method used.

4. **Rate Limits:** Rate limits on GHES instances may be configured differently by the site administrator compared to GitHub.com defaults.
