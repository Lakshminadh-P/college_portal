from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from openai import OpenAI  # OpenAI client (used when quota is available)


app = Flask(__name__)
app.secret_key = "change_this_secret_key"

DATABASE = "database.db"

# OpenAI client (reads OPENAI_API_KEY from environment)
client = OpenAI()

# ----------------- Timetable upload settings -----------------
UPLOAD_FOLDER = os.path.join("static", "uploads", "timetables")
ALLOWED_TIMETABLE_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ----------------- Notes upload settings -----------------
NOTES_UPLOAD_FOLDER = os.path.join("static", "uploads", "notes")
ALLOWED_NOTES_EXTENSIONS = {"pdf", "ppt", "pptx", "doc", "docx"}
os.makedirs(NOTES_UPLOAD_FOLDER, exist_ok=True)


def allowed_timetable_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_TIMETABLE_EXTENSIONS
    )


def allowed_notes_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_NOTES_EXTENSIONS
    )


# ----------------- DB helpers -----------------
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create DB from schema.sql and insert sample data IF database.db does not exist."""
    if os.path.exists(DATABASE):
        return

    conn = get_db_connection()
    # create all tables from schema.sql
    with open("schema.sql", "r") as f:
        conn.executescript(f.read())

    # sample departments
    conn.execute(
        "INSERT INTO departments (name, code) VALUES (?, ?)",
        ("Computer Science & Engineering", "CSE"),
    )
    conn.execute(
        "INSERT INTO departments (name, code) VALUES (?, ?)",
        ("Electronics & Communication", "ECE"),
    )

    # admin user (id = 1)
    admin_pass = generate_password_hash("admin123")
    conn.execute(
        """
        INSERT INTO users (username, password_hash, full_name, email, role, dept_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("admin", admin_pass, "Portal Admin", "admin@college.com", "admin", None),
    )

    # faculty user (id = 2)
    faculty_pass = generate_password_hash("faculty123")
    conn.execute(
        """
        INSERT INTO users (username, password_hash, full_name, email, role, dept_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("faculty1", faculty_pass, "Dr. Faculty One", "faculty1@college.com", "faculty", 1),
    )

    # student user (id = 3)
    student_pass = generate_password_hash("student123")
    conn.execute(
        """
        INSERT INTO users (username, password_hash, full_name, email, role, dept_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("student1", student_pass, "Student One", "student1@college.com", "student", 1),
    )

    # sample course (id = 1)
    conn.execute(
        "INSERT INTO courses (code, name, dept_id, faculty_id) VALUES (?, ?, ?, ?)",
        ("CS101", "Intro to Programming", 1, 2),
    )

    # enrollment (id = 1)
    conn.execute(
        "INSERT INTO enrollments (student_id, course_id, year, semester) VALUES (?, ?, ?, ?)",
        (3, 1, "2025-26", 3),
    )

    # marks for enrollment 1
    conn.execute(
        "INSERT INTO marks (enrollment_id, internal1, internal2, final) VALUES (?, ?, ?, ?)",
        (1, 20, 22, 75),
    )

    # student details for student1
    conn.execute(
        """
        INSERT INTO student_details
            (user_id, roll_no, admission_no, dob, gender, phone, parent_name,
             parent_phone, address, year, semester, section)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            3,
            "1NH21CS001",
            "AD2021CS001",
            "2003-05-15",
            "Male",
            "9876543210",
            "Parent One",
            "9876500000",
            "Bengaluru, Karnataka",
            "II Year",
            3,
            "CSE-A",
        ),
    )

    # attendance for enrollment 1
    conn.execute(
        "INSERT INTO attendance (enrollment_id, total_classes, attended_classes) VALUES (?, ?, ?)",
        (1, 40, 36),
    )

    # remark for student1
    conn.execute(
        """
        INSERT INTO remarks
            (student_id, faculty_id, course_id, remark_type, remark_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            3,
            2,
            1,
            "appreciation",
            "Very active in class and performs well in labs.",
            datetime.now().isoformat(),
        ),
    )

    # announcement
    conn.execute(
        """
        INSERT INTO announcements (title, content, created_at, visible_to)
        VALUES (?, ?, ?, ?)
        """,
        (
            "Welcome to the Portal",
            "This is a sample college portal created using Flask.",
            datetime.now().isoformat(),
            "all",
        ),
    )

    conn.commit()
    conn.close()


def ensure_timetable_table():
    """Extra table just for timetable file uploads."""
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS timetable_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT NOT NULL,
            file_name TEXT NOT NULL,
            uploaded_by INTEGER,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (uploaded_by) REFERENCES users(id)
        )
        """
    )
    conn.commit()
    conn.close()


def ensure_notes_table():
    """Create table for uploaded notes if it doesn't exist."""
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            file_name TEXT NOT NULL,
            uploaded_by INTEGER,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (uploaded_by) REFERENCES users(id)
        )
        """
    )
    conn.commit()
    conn.close()


# ----------------- Syllabus / Timetable data -----------------
DEPARTMENTS_SYLLABUS = {
    "cse": {
        "name": "Computer Science & Engineering",
        "code": "CSE",
        "tagline": "Programming, Algorithms, Data & Systems",
        "semesters": {
            "III": [
                "Data Structures & Applications",
                "Analog & Digital Electronics",
                "Computer Organization",
                "Discrete Mathematical Structures",
                "Object Oriented Programming with Java",
            ],
            "IV": [
                "Design & Analysis of Algorithms",
                "Operating Systems",
                "Microcontrollers & Embedded Systems",
                "Software Engineering",
                "Python Programming Lab",
            ],
        },
    },
    "eee": {
        "name": "Electrical & Electronics Engineering",
        "code": "EEE",
        "tagline": "Power systems, machines & electronics",
        "semesters": {
            "III": [
                "Network Analysis",
                "DC Machines & Transformers",
                "Analog Electronic Circuits",
                "Digital System Design",
            ]
        },
    },
    "ise": {
        "name": "Information Science & Engineering",
        "code": "ISE",
        "tagline": "Information systems, databases & analytics",
        "semesters": {
            "III": [
                "Data Structures",
                "Database Management Systems",
                "Computer Networks",
                "Unix & Shell Programming",
            ]
        },
    },
    "ce": {
        "name": "Civil Engineering",
        "code": "CE",
        "tagline": "Structures, construction & environment",
        "semesters": {
            "III": [
                "Strength of Materials",
                "Building Materials & Construction",
                "Surveying",
                "Fluid Mechanics",
            ]
        },
    },
    "mechanical": {
        "name": "Mechanical Engineering",
        "code": "ME",
        "tagline": "Machines, manufacturing & thermal systems",
        "semesters": {
            "III": [
                "Mechanics of Materials",
                "Thermodynamics",
                "Manufacturing Process",
                "Machine Drawing",
            ]
        },
    },
    "ds": {
        "name": "Data Science",
        "code": "DS",
        "tagline": "Data analytics, ML & visualization",
        "semesters": {
            "III": [
                "Probability & Statistics",
                "Data Structures using Python",
                "Introduction to Data Science",
                "Database Systems",
            ]
        },
    },
    "aiml": {
        "name": "Artificial Intelligence & Machine Learning",
        "code": "AIML",
        "tagline": "AI fundamentals, ML, and neural networks",
        "semesters": {
            "III": [
                "Linear Algebra for AI",
                "Data Structures & Algorithms",
                "Introduction to AI",
                "Python for Machine Learning",
            ]
        },
    },
}

TIMETABLE = {
    "CSE-A": {
        "title": "CSE - III Sem, Section A",
        "days": {
            "Monday": ["DSA", "OS", "Break", "Maths", "OOP Lab"],
            "Tuesday": ["CO", "DSA", "Break", "SE", "Sports"],
            "Wednesday": ["OS", "CO", "Break", "Python Lab", "Python Lab"],
            "Thursday": ["Maths", "DSA", "Break", "SE", "Library"],
            "Friday": ["CO", "OS", "Break", "DSA Tutorial", "Club Activity"],
        },
    }
}


# --------------- Offline exam-style fallback answer ----------
def offline_exam_answer(question: str) -> str:
    """Simple rule-based exam-style answer used when LLM API fails."""
    q = question.lower()

    # --- DBMS general ---
    if "dbms" in q or "database management" in q or ("database" in q and "normalization" not in q):
        return (
            "DBMS – 10-mark answer:\n"
            "1. Definition: A Database Management System (DBMS) is software that allows users to "
            "define, create, maintain and control access to a database.\n"
            "2. Need: Overcomes file system problems like redundancy, inconsistency, difficulty in "
            "access, poor security and integrity.\n"
            "3. Components: Hardware, DBMS software, data, users (DBA, application programmer, end "
            "users) and procedures.\n"
            "4. Data models: Hierarchical, network, relational, object-oriented etc. Most modern "
            "systems use the relational data model.\n"
            "5. Functions: Data storage, retrieval & update, transaction management, concurrency "
            "control, backup & recovery, security and integrity enforcement.\n"
            "6. Advantages: Reduced redundancy, data consistency, data sharing, data independence, "
            "better security and centralized control.\n"
            "7. Examples: MySQL, Oracle, SQL Server, PostgreSQL etc.\n"
            "8. Applications: Banking, college portals, airline reservation, e-commerce, hospitals.\n"
        )

    # --- NoSQL specific ---
    if "nosql" in q:
        return (
            "NoSQL – 10-mark answer:\n"
            "1. Meaning: NoSQL stands for 'Not Only SQL'. It is a class of database systems that do "
            "not strictly follow the traditional relational (table-based) model.\n"
            "2. Motivation: Designed for huge volumes of data, high read/write throughput, "
            "horizontal scalability and flexible schemas used in modern web and big-data applications.\n"
            "3. Characteristics:\n"
            "   • Schema-less or flexible schema (no fixed tables/columns).\n"
            "   • Horizontal scaling using sharding and replication.\n"
            "   • Often follow BASE properties (Basically Available, Soft state, Eventual consistency) "
            "instead of strict ACID.\n"
            "4. Types of NoSQL databases:\n"
            "   • Key–value stores (e.g., Redis, Riak).\n"
            "   • Document stores (e.g., MongoDB, CouchDB).\n"
            "   • Column-family stores (e.g., Cassandra, HBase).\n"
            "   • Graph databases (e.g., Neo4j).\n"
            "5. Advantages:\n"
            "   • Very high scalability and performance.\n"
            "   • Handles unstructured / semi-structured data easily (JSON, logs, social data).\n"
            "   • Works well on clusters of cheap commodity hardware.\n"
            "6. Disadvantages:\n"
            "   • Weaker consistency in some systems (eventual consistency).\n"
            "   • No standard query language like SQL; vendor-specific APIs.\n"
            "   • Fewer mature tools, backups and reporting compared to relational DBMS.\n"
            "7. Use cases: Social networks, real-time analytics, recommendation systems, caching, "
            "content management, IoT and big-data applications.\n"
        )

    # --- Operating System overview ---
    if "operating system" in q or " os " in q or "os?" in q:
        return (
            "Operating System – 10-mark overview:\n"
            "1. Definition: OS is system software that acts as an interface between the user and "
            "computer hardware.\n"
            "2. Main functions: process management, memory management, file system management, "
            "I/O device management, security and accounting.\n"
            "3. Types: batch, time-sharing, real-time, distributed, multiprogramming, multitasking, "
            "multiuser OS.\n"
            "4. Process management: process states, PCB, context switch, and CPU scheduling algorithms "
            "(FCFS, SJF, Priority, Round Robin).\n"
            "5. Memory management: paging, segmentation, virtual memory, demand paging, page "
            "replacement.\n"
            "6. File system: directory structures, file operations, allocation methods (contiguous, "
            "linked, indexed).\n"
            "7. Examples: Windows, Linux, Unix, Android, iOS.\n"
        )

    # --- OOP / Java overview ---
    if "oops" in q or "object oriented" in q or "java" in q:
        return (
            "OOP / Java – key points:\n"
            "1. Core concepts: class, object, abstraction, encapsulation, inheritance, polymorphism "
            "and message passing.\n"
            "2. Advantages: modularity, reusability, extensibility, easier maintenance and closer "
            "mapping to real-world problems.\n"
            "3. Java features: platform independent (JVM), simple, secure, multithreaded, robust, "
            "object-oriented, rich class libraries.\n"
            "4. Example: A class Student with data members usn, name, marks and methods to read and "
            "display details illustrates encapsulation.\n"
        )

    # --- generic fallback ---
    return (
        "Exam-style explanation:\n"
        "- Break down the answer into definition, need/importance, main components,\n"
        "  working/principle, advantages, disadvantages and applications.\n"
        "- Write points in order with proper headings and underline key terms.\n"
        "- For 10-mark questions usually 8–10 well-explained points are enough.\n"
    )


# ----------------- auth decorator -----------------
def login_required(role=None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("You are not authorized to view that page.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        wrapper.__name__ = fn.__name__
        return wrapper

    return decorator


# ----------------- public routes -----------------
@app.route("/")
def home():
    conn = get_db_connection()
    announcements = conn.execute(
        "SELECT * FROM announcements WHERE visible_to = 'all' ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    conn.close()

    departments = []
    for key, info in DEPARTMENTS_SYLLABUS.items():
        departments.append(
            {
                "key": key,
                "code": info["code"],
                "name": info["name"],
                "tagline": info["tagline"],
            }
        )

    return render_template(
        "home.html", announcements=announcements, departments=departments
    )


@app.route("/syllabus")
def syllabus_home():
    departments = []
    for key, info in DEPARTMENTS_SYLLABUS.items():
        departments.append(
            {
                "key": key,
                "code": info["code"],
                "name": info["name"],
                "tagline": info["tagline"],
            }
        )
    return render_template("syllabus_home.html", departments=departments)


@app.route("/syllabus/<dept_code>")
def department_syllabus(dept_code):
    dept_code = dept_code.lower()
    if dept_code not in DEPARTMENTS_SYLLABUS:
        flash("Invalid department code.", "danger")
        return redirect(url_for("syllabus_home"))
    info = DEPARTMENTS_SYLLABUS[dept_code]
    return render_template("syllabus_department.html", dept=info)


# ----------------- auth routes -----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    role = session.get("role")
    if role == "admin":
        return redirect(url_for("admin_dashboard"))
    if role == "student":
        return redirect(url_for("student_dashboard"))
    if role == "faculty":
        return redirect(url_for("faculty_dashboard"))
    return redirect(url_for("home"))


# ----------------- admin routes -----------------
@app.route("/admin/dashboard")
@login_required(role="admin")
def admin_dashboard():
    conn = get_db_connection()
    total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    total_students = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE role='student'"
    ).fetchone()["c"]
    total_faculty = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE role='faculty'"
    ).fetchone()["c"]
    total_courses = conn.execute(
        "SELECT COUNT(*) AS c FROM courses"
    ).fetchone()["c"]
    conn.close()
    return render_template(
        "dashboard_admin.html",
        total_users=total_users,
        total_students=total_students,
        total_faculty=total_faculty,
        total_courses=total_courses,
    )


@app.route("/admin/users")
@login_required(role="admin")
def admin_users():
    conn = get_db_connection()
    users = conn.execute(
        """
        SELECT u.*, d.name AS dept_name
        FROM users u
        LEFT JOIN departments d ON u.dept_id = d.id
        """
    ).fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/add", methods=["GET", "POST"])
@login_required(role="admin")
def admin_add_user():
    conn = get_db_connection()
    departments = conn.execute("SELECT * FROM departments").fetchall()

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip()
        role = request.form["role"]
        dept_id = request.form.get("dept_id") or None

        # extra fields (mainly for students)
        dob = request.form.get("dob") or None
        gender = request.form.get("gender") or None
        phone = request.form.get("phone") or None
        roll_no = request.form.get("roll_no") or None
        admission_no = request.form.get("admission_no") or None
        parent_name = request.form.get("parent_name") or None
        parent_phone = request.form.get("parent_phone") or None
        address = request.form.get("address") or None
        year = request.form.get("year") or None
        semester = request.form.get("semester") or None
        section = request.form.get("section") or None

        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            flash("Username already exists. Choose another.", "danger")
        else:
            password_hash = generate_password_hash(password)
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, full_name, email, role, dept_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username, password_hash, full_name, email, role, dept_id),
            )
            user_id = cur.lastrowid

            # If this is a student, also insert into student_details
            if role == "student":
                conn.execute(
                    """
                    INSERT INTO student_details
                        (user_id, roll_no, admission_no, dob, gender, phone,
                         parent_name, parent_phone, address, year, semester, section)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        roll_no,
                        admission_no,
                        dob,
                        gender,
                        phone,
                        parent_name,
                        parent_phone,
                        address,
                        year,
                        int(semester) if semester else None,
                        section,
                    ),
                )

            conn.commit()
            flash(f"{role.title()} created successfully!", "success")
            conn.close()
            return redirect(url_for("admin_users"))

    conn.close()
    return render_template("admin_add_user.html", departments=departments)


@app.route("/admin/courses", methods=["GET", "POST"])
@login_required(role="admin")
def admin_courses():
    conn = get_db_connection()

    if request.method == "POST":
        code = request.form["code"].strip()
        name = request.form["name"].strip()
        dept_id = request.form["dept_id"]
        faculty_id = request.form.get("faculty_id") or None

        existing = conn.execute(
            "SELECT id FROM courses WHERE code = ?", (code,)
        ).fetchone()
        if existing:
            flash("Course code already exists.", "danger")
        else:
            conn.execute(
                "INSERT INTO courses (code, name, dept_id, faculty_id) VALUES (?, ?, ?, ?)",
                (code, name, dept_id, faculty_id),
            )
            conn.commit()
            flash("Course added successfully!", "success")

    courses = conn.execute(
        """
        SELECT c.*, d.name AS dept_name, u.full_name AS faculty_name
        FROM courses c
        LEFT JOIN departments d ON c.dept_id = d.id
        LEFT JOIN users u ON c.faculty_id = u.id
        ORDER BY c.code
        """
    ).fetchall()

    departments = conn.execute("SELECT * FROM departments").fetchall()
    faculty = conn.execute(
        "SELECT id, full_name, username FROM users WHERE role = 'faculty'"
    ).fetchall()

    conn.close()
    return render_template(
        "admin_courses.html",
        courses=courses,
        departments=departments,
        faculty=faculty,
    )


# ----------------- student routes -----------------
@app.route("/student/dashboard")
@login_required(role="student")
def student_dashboard():
    user_id = session["user_id"]
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    enrollments = conn.execute(
        """
        SELECT e.id AS enrollment_id, c.code, c.name, e.year, e.semester
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        WHERE e.student_id = ?
        """,
        (user_id,),
    ).fetchall()
    announcements = conn.execute(
        """
        SELECT * FROM announcements
        WHERE visible_to IN ('all', 'student')
        ORDER BY created_at DESC LIMIT 5
        """
    ).fetchall()
    conn.close()
    return render_template(
        "dashboard_student.html",
        user=user,
        enrollments=enrollments,
        announcements=announcements,
    )


@app.route("/student/profile")
@login_required(role="student")
def student_profile():
    user_id = session["user_id"]
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    detail = conn.execute(
        "SELECT * FROM student_details WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    dept = None
    if user["dept_id"]:
        dept = conn.execute(
            "SELECT * FROM departments WHERE id = ?",
            (user["dept_id"],),
        ).fetchone()
    conn.close()
    return render_template("student_profile.html", user=user, detail=detail, dept=dept)


@app.route("/student/marks")
@login_required(role="student")
def student_marks():
    user_id = session["user_id"]
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT c.code, c.name, m.internal1, m.internal2, m.final
        FROM marks m
        JOIN enrollments e ON m.enrollment_id = e.id
        JOIN courses c ON e.course_id = c.id
        WHERE e.student_id = ?
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return render_template("student_marks.html", marks=rows)


@app.route("/student/attendance")
@login_required(role="student")
def student_attendance():
    user_id = session["user_id"]
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT c.code, c.name,
               a.total_classes, a.attended_classes,
               CASE
                 WHEN a.total_classes > 0
                 THEN ROUND( (CAST(a.attended_classes AS FLOAT) / a.total_classes) * 100, 2 )
                 ELSE NULL
               END AS percentage
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        LEFT JOIN attendance a ON a.enrollment_id = e.id
        WHERE e.student_id = ?
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return render_template("student_attendance.html", attendance=rows)


@app.route("/student/remarks")
@login_required(role="student")
def student_remarks():
    user_id = session["user_id"]
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT r.*, u.full_name AS faculty_name,
               c.code AS course_code, c.name AS course_name
        FROM remarks r
        JOIN users u ON r.faculty_id = u.id
        LEFT JOIN courses c ON r.course_id = c.id
        WHERE r.student_id = ?
        ORDER BY r.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return render_template("student_remarks.html", remarks=rows)


@app.route("/student/notes")
@login_required(role="student")
def student_notes():
    user_id = session["user_id"]
    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT c.id AS course_id,
               c.code,
               c.name,
               n.id AS notes_id,
               n.title,
               n.file_name,
               n.uploaded_at
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        LEFT JOIN notes_files n ON n.course_id = c.id
        WHERE e.student_id = ?
        ORDER BY c.code, n.uploaded_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return render_template("student_notes.html", notes_rows=rows)


@app.route("/student/timetable")
@login_required(role="student")
def student_timetable():
    user_id = session["user_id"]
    conn = get_db_connection()
    row = conn.execute(
        "SELECT section FROM student_details WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    section = row["section"] if row and row["section"] else "CSE-A"

    tt_file = conn.execute(
        """
        SELECT * FROM timetable_files
        WHERE section = ?
        ORDER BY uploaded_at DESC
        LIMIT 1
        """,
        (section,),
    ).fetchone()
    conn.close()

    file_url = None
    is_pdf = False
    if tt_file:
        file_url = url_for(
            "static",
            filename=f"uploads/timetables/{tt_file['file_name']}",
        )
        is_pdf = tt_file["file_name"].lower().endswith(".pdf")

    tt = TIMETABLE.get(section) or TIMETABLE.get("CSE-A")

    return render_template(
        "student_timetable.html",
        section=section,
        file_url=file_url,
        is_pdf=is_pdf,
        timetable=tt,
    )


# ----------------- faculty routes -----------------
@app.route("/faculty/dashboard")
@login_required(role="faculty")
def faculty_dashboard():
    user_id = session["user_id"]
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    courses = conn.execute(
        "SELECT * FROM courses WHERE faculty_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return render_template("dashboard_faculty.html", user=user, courses=courses)


@app.route("/faculty/marks", methods=["GET", "POST"])
@login_required(role="faculty")
def faculty_marks():
    conn = get_db_connection()
    user_id = session["user_id"]

    courses = conn.execute(
        "SELECT * FROM courses WHERE faculty_id = ?", (user_id,)
    ).fetchall()

    selected_course_id = request.args.get("course_id")
    students = []

    if selected_course_id:
        students = conn.execute(
            """
            SELECT e.id AS enrollment_id, u.full_name, u.username,
                   c.code, c.name,
                   m.internal1, m.internal2, m.final
            FROM enrollments e
            JOIN users u ON e.student_id = u.id
            JOIN courses c ON e.course_id = c.id
            LEFT JOIN marks m ON m.enrollment_id = e.id
            WHERE e.course_id = ?
            """,
            (selected_course_id,),
        ).fetchall()

    if request.method == "POST":
        enrollment_id = request.form["enrollment_id"]
        internal1 = request.form.get("internal1") or None
        internal2 = request.form.get("internal2") or None
        final = request.form.get("final") or None

        existing = conn.execute(
            "SELECT * FROM marks WHERE enrollment_id = ?",
            (enrollment_id,),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE marks SET internal1=?, internal2=?, final=? WHERE enrollment_id=?",
                (internal1, internal2, final, enrollment_id),
            )
        else:
            conn.execute(
                "INSERT INTO marks (enrollment_id, internal1, internal2, final) VALUES (?, ?, ?, ?)",
                (enrollment_id, internal1, internal2, final),
            )
        conn.commit()
        flash("Marks saved successfully!", "success")
        conn.close()
        return redirect(url_for("faculty_marks", course_id=selected_course_id))

    conn.close()
    return render_template(
        "faculty_marks.html",
        courses=courses,
        students=students,
        selected_course_id=selected_course_id,
    )


@app.route("/faculty/attendance", methods=["GET", "POST"])
@login_required(role="faculty")
def faculty_attendance():
    conn = get_db_connection()
    user_id = session["user_id"]

    courses = conn.execute(
        "SELECT * FROM courses WHERE faculty_id = ?", (user_id,)
    ).fetchall()

    selected_course_id = request.args.get("course_id")
    students = []

    if selected_course_id:
        students = conn.execute(
            """
            SELECT e.id AS enrollment_id, u.full_name, u.username,
                   a.total_classes, a.attended_classes
            FROM enrollments e
            JOIN users u ON e.student_id = u.id
            LEFT JOIN attendance a ON a.enrollment_id = e.id
            WHERE e.course_id = ?
            """,
            (selected_course_id,),
        ).fetchall()

    if request.method == "POST":
        enrollment_id = request.form["enrollment_id"]
        total_classes = int(request.form.get("total_classes") or 0)
        attended_classes = int(request.form.get("attended_classes") or 0)

        existing = conn.execute(
            "SELECT * FROM attendance WHERE enrollment_id = ?",
            (enrollment_id,),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE attendance SET total_classes=?, attended_classes=? WHERE enrollment_id=?",
                (total_classes, attended_classes, enrollment_id),
            )
        else:
            conn.execute(
                "INSERT INTO attendance (enrollment_id, total_classes, attended_classes) VALUES (?, ?, ?)",
                (enrollment_id, total_classes, attended_classes),
            )
        conn.commit()
        flash("Attendance updated successfully!", "success")
        conn.close()
        return redirect(url_for("faculty_attendance", course_id=selected_course_id))

    conn.close()
    return render_template(
        "faculty_attendance.html",
        courses=courses,
        students=students,
        selected_course_id=selected_course_id,
    )


@app.route("/faculty/remarks", methods=["GET", "POST"])
@login_required(role="faculty")
def faculty_remarks():
    conn = get_db_connection()
    user_id = session["user_id"]

    courses = conn.execute(
        "SELECT * FROM courses WHERE faculty_id = ?", (user_id,)
    ).fetchall()

    selected_course_id = request.args.get("course_id")
    students = []

    if selected_course_id:
        students = conn.execute(
            """
            SELECT DISTINCT u.id AS student_id, u.full_name, u.username
            FROM enrollments e
            JOIN users u ON e.student_id = u.id
            WHERE e.course_id = ?
            """,
            (selected_course_id,),
        ).fetchall()

    if request.method == "POST":
        student_id = request.form["student_id"]
        course_id = request.form["course_id"]
        remark_type = request.form.get("remark_type") or "general"
        remark_text = request.form["remark_text"]

        conn.execute(
            """
            INSERT INTO remarks (student_id, faculty_id, course_id, remark_type, remark_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (student_id, user_id, course_id, remark_type, remark_text, datetime.now().isoformat()),
        )
        conn.commit()
        flash("Remark added successfully!", "success")
        conn.close()
        return redirect(url_for("faculty_remarks", course_id=course_id))

    conn.close()
    return render_template(
        "faculty_remarks.html",
        courses=courses,
        students=students,
        selected_course_id=selected_course_id,
    )


@app.route("/faculty/timetable-upload", methods=["GET", "POST"])
@login_required(role="faculty")
def faculty_timetable_upload():
    conn = get_db_connection()
    user_id = session["user_id"]
    default_section = "CSE-A"

    if request.method == "POST":
        section = request.form.get("section", default_section)
        file = request.files.get("timetable_file")

        if not file or file.filename == "":
            flash("Please choose a file to upload.", "danger")
            conn.close()
            return redirect(url_for("faculty_timetable_upload"))

        if not allowed_timetable_file(file.filename):
            flash("Only PNG, JPG, JPEG, or PDF files are allowed.", "danger")
            conn.close()
            return redirect(url_for("faculty_timetable_upload"))

        filename = secure_filename(file.filename)
        timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
        filename_with_ts = f"{timestamp_str}_{filename}"
        save_path = os.path.join(UPLOAD_FOLDER, filename_with_ts)
        file.save(save_path)

        conn.execute(
            """
            INSERT INTO timetable_files (section, file_name, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?)
            """,
            (section, filename_with_ts, user_id, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        flash("Timetable uploaded successfully!", "success")
        return redirect(url_for("faculty_timetable_upload"))

    latest = conn.execute(
        """
        SELECT tf.*, u.full_name AS faculty_name
        FROM timetable_files tf
        LEFT JOIN users u ON tf.uploaded_by = u.id
        WHERE tf.section = ?
        ORDER BY tf.uploaded_at DESC
        LIMIT 1
        """,
        (default_section,),
    ).fetchone()
    conn.close()

    return render_template(
        "faculty_timetable_upload.html",
        latest=latest,
        default_section=default_section,
    )


@app.route("/faculty/notes-upload", methods=["GET", "POST"])
@login_required(role="faculty")
def faculty_notes_upload():
    conn = get_db_connection()
    user_id = session["user_id"]

    courses = conn.execute(
        "SELECT * FROM courses WHERE faculty_id = ?",
        (user_id,),
    ).fetchall()

    if request.method == "POST":
        course_id = request.form["course_id"]
        title = request.form["title"].strip()
        file = request.files.get("notes_file")

        if not course_id or not title:
            flash("Please select course and enter title.", "danger")
            conn.close()
            return redirect(url_for("faculty_notes_upload"))

        if not file or file.filename == "":
            flash("Please choose a file to upload.", "danger")
            conn.close()
            return redirect(url_for("faculty_notes_upload"))

        if not allowed_notes_file(file.filename):
            flash("Allowed formats: pdf, ppt, pptx, doc, docx.", "danger")
            conn.close()
            return redirect(url_for("faculty_notes_upload"))

        filename = secure_filename(file.filename)
        timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
        final_name = f"{timestamp_str}_{filename}"
        save_path = os.path.join(NOTES_UPLOAD_FOLDER, final_name)
        file.save(save_path)

        conn.execute(
            """
            INSERT INTO notes_files (course_id, title, file_name, uploaded_by, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (course_id, title, final_name, user_id, datetime.now().isoformat()),
        )
        conn.commit()
        flash("Notes uploaded successfully!", "success")
        conn.close()
        return redirect(url_for("faculty_notes_upload"))

    recent = conn.execute(
        """
        SELECT n.*, c.code AS course_code, c.name AS course_name
        FROM notes_files n
        JOIN courses c ON n.course_id = c.id
        WHERE n.uploaded_by = ?
        ORDER BY n.uploaded_at DESC
        LIMIT 10
        """,
        (user_id,),
    ).fetchall()
    conn.close()

    return render_template(
        "faculty_notes_upload.html",
        courses=courses,
        recent=recent,
    )


# ----------------- AI Chatbot (LLM Tutor + offline fallback) -----------------
@app.route("/chatbot", methods=["GET", "POST"])
@login_required()  # any logged-in user can access
def chatbot():
    chat_history = []

    if request.method == "POST":
        user_message = request.form.get("message", "").strip()
        if user_message:
            chat_history.append(("You", user_message))

            bot_reply = None

            # Try live LLM first, if key exists
            if os.getenv("OPENAI_API_KEY"):
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",  # change to a model you have access to
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are a helpful college exam tutor. "
                                    "Explain CS/IT/Engineering concepts clearly, step by step, "
                                    "using simple language and relevant examples."
                                ),
                            },
                            {"role": "user", "content": user_message},
                        ],
                        max_tokens=500,
                        temperature=0.3,
                    )
                    bot_reply = response.choices[0].message.content
                except Exception:
                    # any error (including quota issues) → fall back to offline answer
                    bot_reply = (
                        offline_exam_answer(user_message)
                        + "\n\n(Note: Live AI quota is over or unavailable, "
                        "so this is an offline exam-style answer.)"
                    )
            else:
                # no key set → offline directly
                bot_reply = (
                    offline_exam_answer(user_message)
                    + "\n\n(Note: Live AI key not configured, showing offline answer.)"
                )

            chat_history.append(("TutorBot", bot_reply))

    return render_template("chatbot.html", chat_history=chat_history)


# ----------------- main -----------------
if __name__ == "__main__":
    init_db()
    ensure_timetable_table()
    ensure_notes_table()
    app.run(debug=True)
