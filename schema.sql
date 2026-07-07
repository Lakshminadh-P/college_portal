DROP TABLE IF EXISTS remarks;
DROP TABLE IF EXISTS attendance;
DROP TABLE IF EXISTS student_details;
DROP TABLE IF EXISTS marks;
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS departments;
DROP TABLE IF EXISTS announcements;

CREATE TABLE departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL, -- 'admin', 'student', 'faculty'
    dept_id INTEGER,
    FOREIGN KEY (dept_id) REFERENCES departments(id)
);

CREATE TABLE courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    dept_id INTEGER,
    faculty_id INTEGER,
    FOREIGN KEY (dept_id) REFERENCES departments(id),
    FOREIGN KEY (faculty_id) REFERENCES users(id)
);

CREATE TABLE enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    year TEXT,
    semester INTEGER,
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id INTEGER NOT NULL,
    internal1 INTEGER,
    internal2 INTEGER,
    final INTEGER,
    FOREIGN KEY (enrollment_id) REFERENCES enrollments(id)
);

CREATE TABLE announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    visible_to TEXT NOT NULL -- 'all', 'student', 'faculty'
);

CREATE TABLE student_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    roll_no TEXT NOT NULL,
    admission_no TEXT,
    dob TEXT,
    gender TEXT,
    phone TEXT,
    parent_name TEXT,
    parent_phone TEXT,
    address TEXT,
    year TEXT,
    semester INTEGER,
    section TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id INTEGER NOT NULL,
    total_classes INTEGER NOT NULL DEFAULT 0,
    attended_classes INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (enrollment_id) REFERENCES enrollments(id)
);

CREATE TABLE remarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    faculty_id INTEGER NOT NULL,
    course_id INTEGER,
    remark_type TEXT,
    remark_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (faculty_id) REFERENCES users(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
