from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv
import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
import os
from openai import APIError, APITimeoutError, OpenAI
from datetime import datetime
import json
from io import BytesIO
import re
import subprocess
import sys
import yaml
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from resume_paths import get_resume_output_path

load_dotenv()

app = Flask(__name__, static_folder=None)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "150"))
client = OpenAI(api_key=api_key, timeout=OPENAI_TIMEOUT_SECONDS)

# Existing YAML files are only used for one-time migration into PostgreSQL.
PROFILES_DIR = Path("profiles")
RAW_DATABASE_URL = os.getenv("DATABASE_URL")
if not RAW_DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")
DATABASE_URL = None

TAILOR_USER_ID = int(os.getenv("TAILOR_USER_ID", "1"))
MIGRATE_PROFILES_FROM_YAML = (
    os.getenv("MIGRATE_PROFILES_FROM_YAML", "true").lower() == "true"
)
RESUME_S3_BUCKET = (
    os.getenv("RESUME_S3_BUCKET")
    or os.getenv("AWS_S3_BUCKET_NAME")
    or os.getenv("S3_BUCKET_NAME")
)
DB_INITIALIZED = False


def get_db_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def database_ssl_enabled():
    value = os.getenv("DATABASE_SSL", "false").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("DATABASE_SSL must be true or false")


def normalize_database_url(value):
    parsed = urlsplit(value)
    query = {
        key: val
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in {"pgbouncer", "sslmode"}
    }
    if database_ssl_enabled():
        query["sslmode"] = "require"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


DATABASE_URL = normalize_database_url(RAW_DATABASE_URL)


def ensure_database():
    """Ensure shared bid profile storage exists and optionally import legacy YAML profiles once."""
    global DB_INITIALIZED
    if DB_INITIALIZED:
        return

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bid_profiles (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    location TEXT,
                    phone TEXT,
                    email TEXT,
                    linkedin TEXT,
                    years_of_experience TEXT,
                    companies JSONB NOT NULL DEFAULT '[]'::jsonb,
                    education JSONB NOT NULL DEFAULT '[]'::jsonb,
                    resume_text TEXT,
                    color_scheme TEXT NOT NULL DEFAULT 'green',
                    profile_badge TEXT NOT NULL DEFAULT 'SWE',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS location TEXT")
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS phone TEXT")
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS email TEXT")
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS linkedin TEXT")
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS years_of_experience TEXT")
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS companies JSONB NOT NULL DEFAULT '[]'::jsonb")
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS education JSONB NOT NULL DEFAULT '[]'::jsonb")
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS resume_text TEXT")
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS color_scheme TEXT NOT NULL DEFAULT 'green'")
            cur.execute("ALTER TABLE bid_profiles ADD COLUMN IF NOT EXISTS profile_badge TEXT NOT NULL DEFAULT 'SWE'")
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS bid_profiles_user_name_lower_idx
                ON bid_profiles (user_id, lower(name))
                """
            )
            cur.execute(
                "SELECT COUNT(*) AS count FROM bid_profiles WHERE user_id = %s",
                (TAILOR_USER_ID,),
            )
            count = cur.fetchone()["count"]

        if count == 0 and MIGRATE_PROFILES_FROM_YAML:
            migrate_profiles_from_yaml(conn)

    DB_INITIALIZED = True


def parse_profile_timestamp(value):
    if not value:
        return datetime.now()
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def migrate_profiles_from_yaml(conn):
    if not PROFILES_DIR.exists():
        return

    for filepath in sorted(PROFILES_DIR.glob("profile_*.yaml")):
        with filepath.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not data.get("name"):
            continue

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bid_profiles (
                    user_id, name, location, phone, email, linkedin,
                    years_of_experience, companies, education,
                    resume_text, color_scheme, profile_badge, created_at, updated_at
                )
                VALUES (
                    %(user_id)s, %(name)s, %(location)s, %(phone)s, %(email)s,
                    %(linkedin)s, %(years_of_experience)s, %(companies)s,
                    %(education)s, %(resume_text)s, %(color_scheme)s, %(profile_badge)s,
                    %(created_at)s, %(updated_at)s
                )
                ON CONFLICT DO NOTHING
                """,
                {
                    "user_id": TAILOR_USER_ID,
                    "name": data.get("name", ""),
                    "location": data.get("location", ""),
                    "phone": data.get("phone", ""),
                    "email": data.get("email", ""),
                    "linkedin": data.get("linkedin", ""),
                    "years_of_experience": str(data.get("years_of_experience", "")),
                    "companies": Jsonb(data.get("companies") or []),
                    "education": Jsonb(data.get("education") or []),
                    "resume_text": data.get("resume_text", ""),
                    "color_scheme": data.get("color_scheme", "green"),
                    "profile_badge": data.get("profile_badge", "SWE"),
                    "created_at": parse_profile_timestamp(data.get("created_at")),
                    "updated_at": parse_profile_timestamp(data.get("updated_at")),
                },
            )


def serialize_profile(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "location": row["location"],
        "phone": row["phone"],
        "email": row["email"],
        "linkedin": row["linkedin"],
        "years_of_experience": row["years_of_experience"],
        "companies": row["companies"] or [],
        "education": row["education"] or [],
        "resume_text": row["resume_text"],
        "color_scheme": row.get("color_scheme") or "green",
        "profile_badge": row.get("profile_badge") or "SWE",
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def get_all_profiles():
    """Get list of all profiles from the shared bid_profiles table."""
    ensure_database()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, created_at, updated_at
                FROM bid_profiles
                WHERE user_id = %s
                ORDER BY updated_at DESC
                """,
                (TAILOR_USER_ID,),
            )
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat(),
                }
                for row in cur.fetchall()
            ]


def load_profile(profile_id):
    """Load a profile from the shared bid_profiles table."""
    ensure_database()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM bid_profiles WHERE id = %s AND user_id = %s",
                (profile_id, TAILOR_USER_ID),
            )
            return serialize_profile(cur.fetchone())


def profile_name_exists(name, profile_id=None):
    ensure_database()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if profile_id is None:
                cur.execute(
                    """
                    SELECT 1 FROM bid_profiles
                    WHERE user_id = %s AND lower(name) = lower(%s)
                    """,
                    (TAILOR_USER_ID, name),
                )
            else:
                cur.execute(
                    """
                    SELECT 1 FROM bid_profiles
                    WHERE user_id = %s AND lower(name) = lower(%s) AND id <> %s
                    """,
                    (TAILOR_USER_ID, name, profile_id),
                )
            return cur.fetchone() is not None


def create_profile_record(profile_data):
    """Create a profile in bid_profiles and return its new ID."""
    ensure_database()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bid_profiles (
                    user_id, name, location, phone, email, linkedin, years_of_experience,
                    companies, education, resume_text, color_scheme, profile_badge, created_at, updated_at
                )
                VALUES (
                    %(user_id)s, %(name)s, %(location)s, %(phone)s, %(email)s, %(linkedin)s,
                    %(years_of_experience)s, %(companies)s, %(education)s,
                    %(resume_text)s, %(color_scheme)s, %(profile_badge)s, %(created_at)s, %(updated_at)s
                )
                RETURNING id
                """,
                {
                    **profile_data,
                    "user_id": TAILOR_USER_ID,
                    "companies": Jsonb(profile_data.get("companies") or []),
                    "education": Jsonb(profile_data.get("education") or []),
                    "color_scheme": profile_data.get("color_scheme") or "green",
                    "profile_badge": profile_data.get("profile_badge") or "SWE",
                },
            )
            return cur.fetchone()["id"]


def update_profile_record(profile_id, profile_data):
    """Update a profile in bid_profiles."""
    ensure_database()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bid_profiles
                SET name = %(name)s,
                    location = %(location)s,
                    phone = %(phone)s,
                    email = %(email)s,
                    linkedin = %(linkedin)s,
                    years_of_experience = %(years_of_experience)s,
                    companies = %(companies)s,
                    education = %(education)s,
                    resume_text = %(resume_text)s,
                    color_scheme = %(color_scheme)s,
                    profile_badge = %(profile_badge)s,
                    updated_at = %(updated_at)s
                WHERE id = %(id)s AND user_id = %(user_id)s
                """,
                {
                    **profile_data,
                    "id": profile_id,
                    "user_id": TAILOR_USER_ID,
                    "companies": Jsonb(profile_data.get("companies") or []),
                    "education": Jsonb(profile_data.get("education") or []),
                    "color_scheme": profile_data.get("color_scheme") or "green",
                    "profile_badge": profile_data.get("profile_badge") or "SWE",
                },
            )
            return cur.rowcount > 0


def delete_profile_record(profile_id):
    """Delete a profile from bid_profiles."""
    ensure_database()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bid_profiles WHERE id = %s AND user_id = %s",
                (profile_id, TAILOR_USER_ID),
            )
            return cur.rowcount > 0


def generate_resume(job_description=None, profile_resume=None):
    """Use OpenAI to generate a resume based on job description and optional profile resume"""

    # At least one input must be provided
    if (not job_description or not str(job_description).strip()) and (
        not profile_resume or not str(profile_resume).strip()
    ):
        raise ValueError("Provide a job description or a profile resume.")

    # Build prompt using profile_resume when available, otherwise only job_description
    infer_note = ""
    if profile_resume and profile_resume.strip():
        # If the profile is very short (e.g., only name, years, companies, education), ask the model to infer realistic
        # role titles, responsibilities, and achievement bullets using those seeds.
        profile_len = len(profile_resume.strip())
        minimal_profile = profile_len < 400
        if minimal_profile:
            infer_note = (
                "The provided profile is brief (likely only name, years of experience, companies, and education). "
                "Infer reasonable professional details for a senior software engineer based on these seeds: role titles, "
                "timeframes, measurable achievements, and technologies. Do not invent unverifiable company facts; keep achievements plausible and aligned with the job description.\n\n"
            )

        prompt_body = f"Profile:\n{profile_resume}\n\nJob Description:\n{job_description or 'N/A'}"
    else:
        prompt_body = f"Job Description:\n{job_description}"

    prompt = f"""
    You are an expert resume writer. Create a full, ATS-friendly resume using the information below.

    {infer_note}{prompt_body}

    Instructions:
    - If a full resume/profile is provided, base the output on that content.
    - If only a minimal profile is provided (name, years, companies, education), infer plausible role titles, durations, accomplishments (with metrics when reasonable), and technologies that fit the candidate level and companies listed.
    - Produce experience entries for each company in the profile(company name, dates, and achievement bullets of 20-30 words each)
    - If the experience in the company is between 2-4, use 8 bullets, if 0-2, use 6 bullets for each comapny. If the company is the third or fourth one, use 5 bullets.
    - Avoid '%' through bullets as possible(1-2 is OK per company), include metrics like counts, quantities, time reductions, performance, speed, accuracy, or financial impact - to demonstrate measurable results and technical contribution. 
    - Include a single-string "tech" field per experience and an overall "skills_and_tools" string.
    - Select 6 exact core skills like frameworks or tools or languages that are 85% relevant to the job description.(ex. Python, React, Agile, Docker...)
    - Summary must be exactly *4* lines highlighting the candidate's unique value proposition for the target role with *65* to *70* words.
    - Skills should contain more than 7 large area categories (e.g., Programming Languages, Frameworks, Tools) with 7-9 specific items each
    - Keep language ATS-friendly and professional and grammatically perfect.
    - Name field should be a combination company name in JD and the role and randome number upto 300(no repeat for 50 times)(e.g., "Apple AI Engineer 208" ).
    - Set target_company to the company from the job description. If the company is unavailable, use "Company".
    - Choose the role wisely based on the job description and profile content, ideally matching a title from the profile if possible, but ensuring it aligns well with the job description.
    - **Output ONLY valid JSON**. Do NOT include any extra text, markdown, or explanations.
    - The JSON must match this exact skeleton:
    {{
        "name": "",
        "target_company": "",
        "role" : "",
        "summary": "",
        "core_skills": "",
        "experience": [
            {{
                "company": "",
                "location": "",
                "position": "",
                "start_date": "", // format as "YYYY-MM" (e.g., "2020-03")
                "end_date": "", // format as "YYYY-MM" (e.g., "2020-03")
                "bullets": ["", ""],
                "tech": "" // a comma-separated string of 7 technologies used in this role (e.g., "Python, AWS, Docker")
            }},
            ...
        ],
        "education": [{{
            "degree": "",
            "area": "",
            "institution": "",
            "start_date": "", // format as "YYYY-MM" (e.g., "2020-03")
            "end_date": "" // format as "YYYY-MM" (e.g., "2020-03")
        }}],
        "skills": {{
            "Programming Languages": ["", "", ...],
            "Frameworks": ["", "", ...],
            "Tools": ["", "", ...],
            ...
        }}
    }}
    """

    response = client.responses.create(
        model="gpt-5-mini", input=prompt
    )

    output_text = ""
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    output_text += content.text

    return output_text


def compact_path_part(value, fallback):
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", str(value or ""))
    return cleaned or fallback


def filename_path_part(value, fallback):
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or ""))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or fallback


def infer_company_from_generated_name(generated_name, role):
    name = str(generated_name or "").strip()
    if not name:
        return "Company"

    without_role = name
    if role:
        without_role = re.sub(re.escape(str(role)), "", without_role, flags=re.IGNORECASE)

    without_role = re.sub(r"\b\d{1,3}\b", "", without_role).strip()
    return without_role.split()[0] if without_role else name.split()[0]


def build_resume_s3_key(profile, generated_data, extension):
    profile_folder = compact_path_part(profile.get("name"), "Profile")
    date_folder = datetime.now().strftime("%Y%m%d")

    role = generated_data.get("role") or "Resume"
    company = generated_data.get("target_company") or infer_company_from_generated_name(
        generated_data.get("name"),
        role,
    )

    company_part = filename_path_part(company, "Company")
    role_part = filename_path_part(role, "Job_Title")
    filename = f"{company_part}_{role_part}_resume{extension}"

    return f"{profile_folder}/{date_folder}/{filename}", filename


def get_s3_client():
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    kwargs = {}
    if region:
        kwargs["region_name"] = region
    return boto3.client("s3", **kwargs)


def upload_resume_to_s3(file_path, s3_key):
    if not RESUME_S3_BUCKET:
        raise RuntimeError(
            "AWS S3 bucket is not configured. Set RESUME_S3_BUCKET, AWS_S3_BUCKET_NAME, or S3_BUCKET_NAME."
        )

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Generated PDF was not found at {file_path}")
    if file_path.stat().st_size == 0:
        raise RuntimeError(f"Generated PDF is empty at {file_path}")

    try:
        s3_client = get_s3_client()
        s3_client.upload_file(
            str(file_path),
            RESUME_S3_BUCKET,
            s3_key,
            ExtraArgs={
                "ContentType": "application/pdf",
                "ContentDisposition": f'attachment; filename="{Path(s3_key).name}"',
            },
        )
        uploaded_object = s3_client.head_object(Bucket=RESUME_S3_BUCKET, Key=s3_key)
        return {
            "bucket": RESUME_S3_BUCKET,
            "key": s3_key,
            "uri": f"s3://{RESUME_S3_BUCKET}/{s3_key}",
            "size": uploaded_object.get("ContentLength"),
            "etag": uploaded_object.get("ETag", "").strip('"'),
        }
    except NoCredentialsError as error:
        raise RuntimeError(
            "AWS credentials were not found. Configure AWS credentials or attach an IAM role with S3 write access."
        ) from error
    except ClientError as error:
        aws_error = error.response.get("Error", {})
        code = aws_error.get("Code", "Unknown")
        message = aws_error.get("Message", str(error))
        raise RuntimeError(
            f"S3 upload failed for s3://{RESUME_S3_BUCKET}/{s3_key}: {code}: {message}"
        ) from error
    except BotoCoreError as error:
        raise RuntimeError(
            f"S3 upload failed for s3://{RESUME_S3_BUCKET}/{s3_key}: {error}"
        ) from error


def generateDocxFile(generated, profile):
    data = json.loads(generated)

    cv = {
        "cv": {
            "name": profile["name"],
            "headline": data["role"],
            "location": profile["location"],
            "email": profile["email"],
            "phone": profile["phone"],
            "social_networks": [
                {"network": "LinkedIn", "username": profile["linkedin"]},
                # {"network": "GitHub", "username": data["basics"]["github"]},
            ],
            "sections": {
                "summary": [data["summary"]],
                "core_skills": [data["core_skills"]],
                "experience": [
                    {
                        "company": e["company"],
                        "position": e["position"],
                        "location": e["location"],
                        "tech_stack": e["tech"],
                        "start_date": e["start_date"],
                        "end_date": e["end_date"],
                        "highlights": e["bullets"],
                    }
                    for e in data["experience"]
                ],
                "education": [
                    {
                        "degree": ed["degree"],
                        "area": ed["area"],
                        "institution": ed["institution"],
                        "start_date": ed["start_date"],
                        "end_date": ed["end_date"],
                    }
                    for ed in data["education"]
                ],
                "skills": [
                    {"label": k, "details": ", ".join(v)}
                    for k, v in data["skills"].items()
                ],
            },
        },
        "design": {
            "theme": "engineeringresumes",
            "colors": {"body": "#262726"},
            "page": {
                "top_margin": "0.3in",
                "bottom_margin": "0.3in",
                "left_margin": "0.3in",
                "right_margin": "0.3in",
            },
            "header": {
                "space_below_name": "0.1in",
                "space_below_headline": "0.1in",
                "space_below_connections": "0.2in",
            },
            "templates": {
                "experience_entry": {
                    "main_column": """**POSITION**
                        **COMPANY** - LOCATION
                        HIGHLIGHTS
                        ***Tech stack:*** TECH_STACK
                        """
                },
            },
            "typography": {
                "bold": {"headline": "true"},
                "font_size": {"body": "11pt"},
            },
        }
    }

    s3_key, filename = build_resume_s3_key(profile, data, ".pdf")
    output_path = get_resume_output_path(s3_key)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    yaml.safe_dump(
        cv,  # your AI JSON
        stream=Path("cv.yaml").open("w", encoding="utf-8"),
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "rendercv",
                "render",
                str("cv.yaml"),
                "-pdf",
                str(output_path),
            ],
            check=True,
        )
    finally:
        Path("cv.yaml").unlink(missing_ok=True)

    upload_result = upload_resume_to_s3(output_path, s3_key)
    output_path.unlink(missing_ok=True)
    print(f"PDF generated and uploaded to {upload_result['uri']}")

    return {"filename": filename, "s3_key": s3_key, "s3": upload_result}


@app.route("/download/<path:s3_key>", methods=["GET"])
def download_resume(s3_key):
    if not RESUME_S3_BUCKET:
        return jsonify({"error": "AWS S3 bucket is not configured"}), 500

    try:
        s3_object = get_s3_client().get_object(Bucket=RESUME_S3_BUCKET, Key=s3_key)
        file_stream = BytesIO(s3_object["Body"].read())
        file_stream.seek(0)
        return send_file(
            file_stream,
            mimetype=s3_object.get("ContentType") or "application/pdf",
            as_attachment=True,
            download_name=Path(s3_key).name,
        )
    except ClientError as error:
        aws_error = error.response.get("Error", {})
        code = aws_error.get("Code")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return jsonify({"error": "Generated resume was not found in S3"}), 404
        return jsonify({"error": f"S3 download failed: {code or 'Unknown'}"}), 502
    except BotoCoreError as error:
        return jsonify({"error": f"S3 download failed: {error}"}), 502


@app.route("/api/profiles", methods=["GET"])
def get_profiles():
    """Get all saved profiles"""
    try:
        profiles = get_all_profiles()
        return jsonify({"profiles": profiles})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles/<int:profile_id>", methods=["GET"])
def get_profile(profile_id):
    """Get a specific profile by ID"""
    try:
        profile = load_profile(profile_id)
        if not profile:
            return jsonify({"error": "Profile not found"}), 404
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles", methods=["POST"])
def create_profile():
    """Create a new profile"""
    try:
        data = request.json
        name = data.get("name", "").strip()
        resume_text = data.get("resume_text", "").strip()
        location = data.get("location", "").strip()
        phone = data.get("phone", "").strip()
        email = data.get("email", "").strip()
        linkedin = data.get("linkedin", "").strip()
        years_of_experience = data.get("years_of_experience", "").strip()
        companies = data.get("companies", [])
        education = data.get("education", [])
        color_scheme = data.get("color_scheme", "green").strip() or "green"
        profile_badge = data.get("profile_badge", "SWE").strip().upper() or "SWE"

        if not name:
            return jsonify({"error": "Profile name is required"}), 400
        if profile_badge not in {"ML", "DE", "SWE"}:
            return jsonify({"error": "Profile badge must be ML, DE, or SWE"}), 400

        # If resume_text not provided, generate a basic contact header from provided fields
        if not resume_text:
            parts = [f"Profile: {name}", "=" * 40]
            if location:
                parts.append(f"Location: {location}")
            if phone:
                parts.append(f"Phone: {phone}")
            if email:
                parts.append(f"Email: {email}")
            if linkedin:
                parts.append(f"LinkedIn: {linkedin}")
            resume_text = "\n".join(parts) + "\n"

        if profile_name_exists(name):
            return jsonify({"error": "Profile name already exists"}), 400

        now = datetime.now().isoformat()

        profile_data = {
            "name": name,
            "location": location,
            "phone": phone,
            "email": email,
            "linkedin": linkedin,
            "years_of_experience": years_of_experience,
            "companies": companies,
            "education": education,
            "resume_text": resume_text,
            "color_scheme": color_scheme,
            "profile_badge": profile_badge,
            "created_at": now,
            "updated_at": now,
        }

        profile_id = create_profile_record(profile_data)

        return (
            jsonify(
                {
                    "id": profile_id,
                    "name": name,
                    "message": "Profile created successfully",
                }
            ),
            201,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles/<int:profile_id>", methods=["PUT"])
def update_profile(profile_id):
    """Update an existing profile"""
    try:
        data = request.json
        name = data.get("name", "").strip()
        resume_text = data.get("resume_text", "").strip()
        location = data.get("location", None)
        phone = data.get("phone", None)
        email = data.get("email", None)
        linkedin = data.get("linkedin", None)
        years_of_experience = data.get("years_of_experience", None)
        companies = data.get("companies", None)
        education = data.get("education", None)
        color_scheme = data.get("color_scheme", None)
        profile_badge = data.get("profile_badge", None)

        if (
            not name
            and not resume_text
            and location is None
            and phone is None
            and email is None
            and linkedin is None
            and years_of_experience is None
            and companies is None
            and education is None
            and color_scheme is None
            and profile_badge is None
        ):
            return jsonify({"error": "At least one field must be provided"}), 400

        profile = load_profile(profile_id)
        if not profile:
            return jsonify({"error": "Profile not found"}), 404

        if name and name.lower() != profile["name"].lower():
            if profile_name_exists(name, profile_id):
                return jsonify({"error": "Profile name already exists"}), 400

        if name:
            profile["name"] = name
        if resume_text:
            profile["resume_text"] = resume_text
        if location is not None:
            profile["location"] = location.strip()
        if phone is not None:
            profile["phone"] = phone.strip()
        if email is not None:
            profile["email"] = email.strip()
        if linkedin is not None:
            profile["linkedin"] = linkedin.strip()
        if years_of_experience is not None:
            profile["years_of_experience"] = str(years_of_experience).strip()
        if companies is not None:
            profile["companies"] = companies
        if education is not None:
            profile["education"] = education
        if color_scheme is not None:
            profile["color_scheme"] = color_scheme.strip() or "green"
        if profile_badge is not None:
            normalized_badge = profile_badge.strip().upper() or "SWE"
            if normalized_badge not in {"ML", "DE", "SWE"}:
                return jsonify({"error": "Profile badge must be ML, DE, or SWE"}), 400
            profile["profile_badge"] = normalized_badge

        profile["updated_at"] = datetime.now().isoformat()
        update_profile_record(profile_id, profile)

        return jsonify({"message": "Profile updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/profiles/<int:profile_id>", methods=["DELETE"])
def delete_profile(profile_id):
    """Delete a profile"""
    try:
        if delete_profile_record(profile_id):
            return jsonify({"message": "Profile deleted successfully"})
        else:
            return jsonify({"error": "Profile not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        data = request.json
        job_desc = data.get("jobDescription", "")
        profile_resume = data.get("profileResume", "")

        if not job_desc:
            return jsonify({"error": "Missing job description"}), 400

        generated = generate_resume(
            job_desc, profile_resume if profile_resume else None
        )

        # generate docx file with json
        resume_file = generateDocxFile(generated, data.get("profile", {}))

        return jsonify(
            {
                "generatedResume": generated,
                "filename": resume_file["filename"],
                "s3Key": resume_file["s3_key"],
                "s3Bucket": RESUME_S3_BUCKET,
                "s3": resume_file["s3"],
            }
        )

    except APITimeoutError:
        return jsonify({"error": "OpenAI request timed out. Please try again."}), 504
    except APIError as e:
        return jsonify({"error": f"OpenAI request failed: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_ENV") != "production",
        port=int(os.getenv("PORT", "5000")),
        host="0.0.0.0",
    )
