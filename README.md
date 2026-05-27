# Resume Generator - AI-Powered Resume Generation

A web application that uses OpenAI's GPT-5-Mini to generate or tailor your resume to specific job descriptions.

## Features

- 🎯 Paste your resume and job description
- ✨ AI-powered resume generation using OpenAI
- 📋 Copy generated resume to clipboard
- ⬇️ Download generated resume as text file
- 🎨 Clean, modern web interface

## Setup

### 1. Configure PostgreSQL

The app stores profiles in the shared `bid_profiles` PostgreSQL table used by the jobs web app. Set `DATABASE_URL` in `.env`:

```bash
DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DATABASE
DATABASE_SSL=true
TAILOR_USER_ID=1
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Add Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:

```
OPENAI_API_KEY=sk-your-api-key-here
DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DATABASE
DATABASE_SSL=true
TAILOR_USER_ID=1
MIGRATE_PROFILES_FROM_YAML=true
RESUME_S3_BUCKET=your-resume-bucket
AWS_REGION=us-east-1
```

Get your API key from: https://platform.openai.com/account/api-keys

### 4. Run the Application

```bash
python app.py
```

The application will be available at: `http://localhost:5000`

## Docker Deployment

The Compose file can run a local build or a prebuilt GHCR image.

For local Docker development:

```bash
cp .env.example .env
docker compose up --build -d
```

For EC2 deployment, install Docker and Docker Compose on the instance, then create `/opt/tailor/.env` from `.env.example` and fill in the real secrets. The GitHub Actions workflow copies `docker-compose.yml` to that directory, pulls the GHCR image built for the current commit, and restarts the `resume-tailor` service.

Configure these GitHub repository secrets:

```text
EC2_HOST
EC2_USER
EC2_SSH_KEY
EC2_PORT              # optional, defaults to 22
GHCR_USERNAME         # only needed if the package is private
GHCR_TOKEN            # PAT with read:packages for private packages
```

Optional repository variable:

```text
EC2_APP_DIR           # defaults to /opt/tailor
```

On every push to `main`, the workflow publishes:

```text
ghcr.io/<owner>/<repo>:latest
ghcr.io/<owner>/<repo>:<commit-sha>
```

The EC2 deployment uses the immutable `<commit-sha>` tag so a deployment always runs the same image that the workflow just built.

## Usage

1. **Paste Your Resume**: Enter your current resume in the left textarea
2. **Paste Job Description**: Enter the job description you're applying for in the right textarea
3. **Click "Generate Resume"**: The AI will generate or customize your resume to match the job
4. **Copy or Download**: Use the buttons to copy to clipboard or download as a text file

## How It Works

- The application sends your resume and job description to OpenAI's GPT-5-Mini model, which:

- Highlights relevant skills and experiences
- Incorporates keywords from the job description
- Reorders bullet points by relevance
- Maintains professional formatting
- Preserves the overall resume structure

## Requirements

- Python 3.8+
- PostgreSQL
- OpenAI API key
- Flask
- python-dotenv
- psycopg

## Data Storage

Profiles are stored in the shared `bid_profiles` PostgreSQL table and scoped to `TAILOR_USER_ID`. On first startup, if that user has no bid profiles and `MIGRATE_PROFILES_FROM_YAML=true`, existing `profiles/profile_*.yaml` files are imported automatically.

RenderCV still receives a temporary YAML file when generating a PDF because that is the format its CLI expects; the app no longer stores profile data in YAML files.

Generated PDFs are also uploaded to S3. The bucket is configured with `RESUME_S3_BUCKET` (or `AWS_S3_BUCKET_NAME` / `S3_BUCKET_NAME`), and AWS credentials are resolved by `boto3` from the environment, shared config, or instance/task role. Resume keys are written as `ProfileName/YYYYMMDD/Company_Job_Title_resume.pdf`, for example `JonZimmerman/20260525/Meta_Senior_Software_Engineer_resume.pdf`.

## File Structure

```
resume/
├── app.py                 # Flask application
├── requirements.txt       # Python dependencies
├── docker-compose.yml     # App and PostgreSQL services
├── .env.example          # Example environment file
├── .env                  # Your local environment (create from .env.example)
├── templates/
│   └── index.html        # Web interface
└── static/
    ├── style.css         # Styling
    └── script.js         # Frontend logic
```

## Tips

- Use clear, detailed job descriptions for better results
- Include all relevant experience in your original resume
- Review the AI-generated resume before submitting
- Experiment with different job descriptions

## Troubleshooting

- **API Key Error**: Make sure your `.env` file is in the project root and properly formatted
- **Database Error**: Ensure PostgreSQL is running and `DATABASE_URL` is correct
- **Connection Error**: Ensure Flask is running on port 5000
- **OpenAI Error**: Check that your API key is valid and has available credits

## License

MIT
# resume-builder
