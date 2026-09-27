import os
import secrets
import string

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from supabase import create_client


# ---------------- LOAD ENVIRONMENT ----------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "SUPABASE_URL or SUPABASE_SECRET_KEY is missing in .env file"
    )

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ---------------- FLASK APP ----------------

app = Flask(__name__)
app.secret_key = "studyguard_secret_key"


# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        if not name or not email or not password:
            flash("Please fill all fields.")
            return redirect(url_for("register"))

        # Check if email already exists
        existing = (
            supabase
            .table("users")
            .select("id")
            .eq("email", email)
            .execute()
        )

        if existing.data:
            flash("Email already registered.")
            return redirect(url_for("register"))

        # Create user
        supabase.table("users").insert({
            "name": name,
            "email": email,
            "password": generate_password_hash(password)
        }).execute()

        flash("Registration successful! Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip()
        password = request.form["password"]

        response = (
            supabase
            .table("users")
            .select("*")
            .eq("email", email)
            .execute()
        )

        user = response.data[0] if response.data else None

        if user and check_password_hash(user["password"], password):

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # Find groups where current user is a member
    member_response = (
        supabase
        .table("group_members")
        .select("group_id")
        .eq("user_id", user_id)
        .execute()
    )

    group_ids = [
        row["group_id"]
        for row in member_response.data
    ]

    groups = []

    if group_ids:
        group_response = (
            supabase
            .table("study_groups")
            .select("id, group_name, group_code")
            .in_("id", group_ids)
            .execute()
        )

        groups = group_response.data

    return render_template(
        "dashboard.html",
        name=session["user_name"],
        groups=groups
    )


# ---------------- CREATE GROUP ----------------

@app.route("/create-group", methods=["GET", "POST"])
def create_group():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        group_name = request.form["group_name"].strip()

        if not group_name:
            flash("Please enter a group name.")
            return redirect(url_for("create_group"))

        # Generate unique 6-character group code
        characters = string.ascii_uppercase + string.digits

        while True:

            group_code = "".join(
                secrets.choice(characters)
                for _ in range(6)
            )

            existing = (
                supabase
                .table("study_groups")
                .select("id")
                .eq("group_code", group_code)
                .execute()
            )

            if not existing.data:
                break

        # Create group
        group_response = (
            supabase
            .table("study_groups")
            .insert({
                "group_name": group_name,
                "group_code": group_code,
                "created_by": session["user_id"]
            })
            .select("id")
            .execute()
        )

        group_id = group_response.data[0]["id"]

        # Add creator as member
        supabase.table("group_members").insert({
            "group_id": group_id,
            "user_id": session["user_id"]
        }).execute()

        flash(
            f"Group created! Your group code is {group_code}"
        )

        return redirect(
            url_for("group", group_id=group_id)
        )

    return render_template("create_group.html")


# ---------------- JOIN GROUP ----------------

@app.route("/join-group", methods=["GET", "POST"])
def join_group():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        group_code = request.form["group_code"].strip().upper()

        # Find group
        response = (
            supabase
            .table("study_groups")
            .select("*")
            .eq("group_code", group_code)
            .execute()
        )

        group = response.data[0] if response.data else None

        if not group:

            flash("Group not found. Check the group code.")
            return redirect(url_for("join_group"))

        group_id = group["id"]
        user_id = session["user_id"]

        # Check if already member
        member_response = (
            supabase
            .table("group_members")
            .select("id")
            .eq("group_id", group_id)
            .eq("user_id", user_id)
            .execute()
        )

        if member_response.data:

            flash("You are already a member of this group.")

            return redirect(
                url_for("group", group_id=group_id)
            )

        # Add member
        supabase.table("group_members").insert({
            "group_id": group_id,
            "user_id": user_id
        }).execute()

        return redirect(
            url_for("group", group_id=group_id)
        )

    return render_template("join_group.html")


# ---------------- GROUP PAGE ----------------

@app.route("/group/<int:group_id>")
def group(group_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # Get group
    group_response = (
        supabase
        .table("study_groups")
        .select("*")
        .eq("id", group_id)
        .execute()
    )

    group_data = (
        group_response.data[0]
        if group_response.data
        else None
    )

    if not group_data:

        flash("Group not found.")
        return redirect(url_for("dashboard"))

    # Check membership
    member_response = (
        supabase
        .table("group_members")
        .select("id")
        .eq("group_id", group_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not member_response.data:

        flash("You are not a member of this group.")
        return redirect(url_for("dashboard"))

    # Get group members
    members_response = (
        supabase
        .table("group_members")
        .select("user_id")
        .eq("group_id", group_id)
        .execute()
    )

    user_ids = [
        row["user_id"]
        for row in members_response.data
    ]

    members = []

    if user_ids:

        users_response = (
            supabase
            .table("users")
            .select("id, name")
            .in_("id", user_ids)
            .execute()
        )

        members = users_response.data

    return render_template(
        "group.html",
        group=group_data,
        members=members
    )


# ---------------- ROUTINE ----------------

@app.route("/routine")
def routine():

    if "user_id" not in session:
        return redirect(url_for("login"))

    response = (
        supabase
        .table("tasks")
        .select("*")
        .eq("user_id", session["user_id"])
        .execute()
    )

    tasks = response.data

    # Sort by date and start time
    tasks.sort(
        key=lambda task: (
            task["task_date"],
            task["start_time"]
        )
    )

    return render_template(
        "routine.html",
        tasks=tasks
    )


# ---------------- ADD TASK ----------------

@app.route("/add-task", methods=["GET", "POST"])
def add_task():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        title = request.form["title"].strip()
        subject = request.form["subject"].strip()
        task_date = request.form["task_date"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]

        if not title or not subject:
            flash("Please fill all fields.")
            return redirect(url_for("add_task"))

        supabase.table("tasks").insert({
            "user_id": session["user_id"],
            "title": title,
            "subject": subject,
            "task_date": task_date,
            "start_time": start_time,
            "end_time": end_time,
            "status": "Pending"
        }).execute()

        return redirect(
            url_for("routine")
        )

    return render_template("add_task.html")


# ---------------- COMPLETE TASK ----------------

@app.route("/complete-task/<int:task_id>", methods=["GET", "POST"])
def complete_task(task_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        proof = request.files.get("proof_photo")
        print("UPLOADED FILE:", proof)

        if not proof or proof.filename == "":
            flash("Please upload a study proof photo.")
            return redirect(url_for("complete_task", task_id=task_id))

        # Unique file name
        filename = f"{session['user_id']}_{task_id}_{secrets.token_hex(8)}_{proof.filename}"

        # Upload photo to Supabase Storage
        file_bytes = proof.read()

        supabase.storage.from_("study-proofs").upload(
            filename,
            file_bytes,
            {"content-type": proof.content_type}
        )

        # Get public URL
        proof_url = supabase.storage.from_("study-proofs").get_public_url(filename)

        # Mark task completed and save proof URL
        supabase.table("tasks").update({
            "status": "Completed",
            "proof_url": proof_url
        }).eq(
            "id", task_id
        ).eq(
            "user_id", session["user_id"]
        ).execute()

        flash("Task completed with photo proof! 🎉")
        return redirect(url_for("routine"))

    return render_template("complete_task.html", task_id=task_id)

# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# ---------------- START APP ----------------

if __name__ == "__main__":
    app.run(debug=True)