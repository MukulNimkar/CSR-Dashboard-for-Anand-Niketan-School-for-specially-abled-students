from flask import Flask, render_template, request, redirect, url_for, make_response, session, flash
import os
import json
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from utils import process_excel, calculate_kpis

app = Flask(__name__)

# =====================================================
# CONFIG
# =====================================================
# Generate a secret key if not provided (needed for sessions)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "csr_dashboard_secret_key_123")

# Vercel's file system is read-only except for /tmp
if os.environ.get("VERCEL"):
    UPLOAD_FOLDER = "/tmp/uploads"
else:
    UPLOAD_FOLDER = "uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# wkhtmltopdf parsing deferred to the export_pdf route

# =====================================================
# AUTHENTICATION HELPERS
# =====================================================
if os.environ.get("VERCEL"):
    CONFIG_FILE = "/tmp/config.json"
else:
    CONFIG_FILE = "config.json"

def get_password_hash():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return data.get("password_hash")
    # Default password is 'admin123' if not set
    default_hash = generate_password_hash("admin123")
    set_password_hash(default_hash)
    return default_hash

def set_password_hash(pwd_hash):
    data = {"password_hash": pwd_hash}
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "logged_in" not in session:
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# =====================================================
# GLOBAL STORAGE
# =====================================================
students_df = None
infra_df = None
kpis = None
upload_logs = []

# =====================================================
# HELPER: GENERATE BAR CHART IMAGE
# =====================================================
def generate_chart(labels, values, filename):
    plt.figure(figsize=(8, 4))
    plt.bar(labels, values)
    plt.xticks(rotation=45)
    plt.tight_layout()
    path = os.path.join("static", filename)
    plt.savefig(path)
    plt.close()
    return os.path.abspath(path)

# =====================================================
# AUTHENTICATION ROUTES
# =====================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password")
        stored_hash = get_password_hash()
        
        if check_password_hash(stored_hash, password):
            session["logged_in"] = True
            next_page = request.args.get("next")
            return redirect(next_page or url_for("overview"))
        else:
            error = "Invalid password. Please try again."
            
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

@app.route("/update_password", methods=["GET", "POST"])
@login_required
def update_password():
    error = None
    success = None
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        stored_hash = get_password_hash()
        
        if not check_password_hash(stored_hash, current_password):
            error = "Current password is incorrect."
        elif new_password != confirm_password:
            error = "New passwords do not match."
        elif len(new_password) < 6:
            error = "New password must be at least 6 characters long."
        else:
            set_password_hash(generate_password_hash(new_password))
            success = "Password updated successfully!"
            
    return render_template("update_password.html", error=error, success=success)

# =====================================================
# OVERVIEW
# =====================================================
@app.route("/")
@login_required
def overview():
    global kpis
    if not kpis:
        return render_template("overview.html", kpis={
            "total_students": 0,
            "avg_attendance": 0,
            "avg_improvement": 0,
            "student_funding_gap": 0,
            "infrastructure_gap": 0,
            "total_funding_gap": 0,
            "funding_coverage_percent": 0,
            "cost_per_student": 0,
            "cost_per_improvement_point": 0,
            "disability_counts": {},
            "therapy_wise_improvement": {},
            "teacher_performance": {},
            "sponsor_contribution": {},
            "disability_wise_improvement": {}
        })

    return render_template("overview.html", kpis=kpis)

# =====================================================
# STUDENTS
# =====================================================
@app.route("/students")
@login_required
def students():
    global students_df, kpis

    if students_df is None:
        return render_template(
            "students.html",
            students=[],
            therapy_labels=[],
            therapy_values=[],
            teacher_labels=[],
            teacher_values=[]
        )

    return render_template(
        "students.html",
        students=students_df.to_dict(orient="records"),
        therapy_labels=list(kpis["therapy_wise_improvement"].keys()),
        therapy_values=list(kpis["therapy_wise_improvement"].values()),
        teacher_labels=list(kpis["teacher_performance"].keys()),
        teacher_values=list(kpis["teacher_performance"].values())
    )

# =====================================================
# INFRASTRUCTURE
# =====================================================
@app.route("/infrastructure")
@login_required
def infrastructure():
    global infra_df

    if infra_df is None or infra_df.empty:
        return render_template(
            "infrastructure.html",
            infra_projects=[],
            chart_labels=[],
            chart_required=[],
            chart_received=[]
        )

    import pandas as pd
    
    # For the chart
    infra_grouped = (
        infra_df.groupby("unit_name")
        .agg(
            total_required_cost=("total_required_cost", "max"),
            total_received=("amount_received", "sum")
        )
        .reset_index()
    )
    
    # For the table (row-by-row)
    infra_projects = []
    unit_gaps = {}
    
    for _, row in infra_df.iterrows():
        unit = row.get("unit_name", "")
        required = float(row.get("total_required_cost", 0) if pd.notna(row.get("total_required_cost")) else 0)
        received = float(row.get("amount_received", 0) if pd.notna(row.get("amount_received")) else 0)
        
        if unit not in unit_gaps:
            unit_gaps[unit] = required
            
        unit_gaps[unit] -= received
        current_gap = unit_gaps[unit]
        
        coverage = 0
        if required > 0:
            coverage = round(((required - current_gap) / required) * 100, 1)
            
        date_rec = row.get("date_fund_received", "")
        if pd.notna(date_rec):
            try:
                date_rec = pd.to_datetime(date_rec).strftime('%d-%m-%Y')
            except Exception:
                date_rec = str(date_rec).split(' ')[0]
        else:
            date_rec = ""
        
        sponsor = row.get("sponsor_name", "")
        sponsor = str(sponsor) if pd.notna(sponsor) else ""
        
        progress = row.get("construction_progress_percent", "")
        progress = progress if pd.notna(progress) else ""
        
        infra_projects.append({
            "unit_name": unit,
            "total_required_cost": required,
            "amount_received": received,
            "gap": current_gap,
            "coverage_percent": coverage,
            "construction_progress_percent": progress,
            "sponsors": sponsor,
            "date_received": date_rec
        })

    # Timeline Logic
    if "date_fund_received" in infra_df.columns:
        # Convert to datetime for sorting
        infra_df_sorted = infra_df.copy()
        
        # Try to parse dates, coercing errors to NaT
        infra_df_sorted['parsed_date'] = pd.to_datetime(infra_df_sorted["date_fund_received"], format='%d-%m-%Y', errors='coerce')
        
        # Drop rows with invalid dates so they don't appear in the timeline
        infra_df_sorted = infra_df_sorted.dropna(subset=['parsed_date'])
        
        # Sort chronologically
        infra_df_sorted = infra_df_sorted.sort_values(by="parsed_date")

        # Group by the parsed_date so identical dates merge properly regardless of text formatting.
        timeline_grouped = (
            infra_df_sorted.groupby("parsed_date", sort=False)
            .agg(total_received=("amount_received", "sum"))
            .reset_index()
        )
        
        # Convert timestamp back to string format DD-MM-YYYY without the time
        timeline_grouped["formatted_date"] = timeline_grouped["parsed_date"].dt.strftime('%d-%m-%Y')
        
        timeline_labels = timeline_grouped["formatted_date"].tolist()
        timeline_values = timeline_grouped["total_received"].tolist()
    else:
        timeline_labels = []
        timeline_values = []


    return render_template(
        "infrastructure.html",
        infra_projects=infra_projects,
        chart_labels=infra_grouped["unit_name"].tolist(),
        chart_required=infra_grouped["total_required_cost"].tolist(),
        chart_received=infra_grouped["total_received"].tolist(),
        timeline_labels=timeline_labels,
        timeline_values=timeline_values
    )

# =====================================================
# DONOR TREE 
# =====================================================
@app.route("/donor_tree")
@login_required
def donor_tree():
    global infra_df

    donors = []
    if infra_df is not None and not infra_df.empty:
        import pandas as pd
        import re
        for _, row in infra_df.iterrows():
            sponsor = row.get("sponsor_name", "")
            if pd.notna(sponsor):
                sponsor_str = str(sponsor).strip()
                if sponsor_str and sponsor_str.lower() != "nan":
                    # Split by comma in case multiple sponsors are in one cell
                    parts = re.split(r'[,]+', sponsor_str)
                    for part in parts:
                        cleaned = part.strip()
                        if cleaned and cleaned not in donors:
                            donors.append(cleaned)
                            
    return render_template("donor_tree.html", donors=donors)

# =====================================================
# UPLOAD + LOGS
# =====================================================
@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    global students_df, infra_df, kpis, upload_logs

    if request.method == "POST":
        file = request.files.get("file")

        if not file or file.filename == "":
            return redirect(url_for("upload"))

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(filepath)

        try:
            students_df, infra_df = process_excel(filepath)
            kpis = calculate_kpis(students_df, infra_df)

            upload_logs.append({
                "filename": file.filename,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "Success"
            })

            return redirect(url_for("overview"))

        except Exception as e:
            upload_logs.append({
                "filename": file.filename,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": f"Error: {str(e)}"
            })

            return redirect(url_for("upload"))

    return render_template("upload.html", logs=upload_logs)

# =====================================================
# RESET LOGS
# =====================================================
@app.route("/reset_logs")
@login_required
def reset_logs():
    global upload_logs
    upload_logs = []
    return redirect(url_for("upload"))

# =====================================================
# EXPORT FULL PROFESSIONAL PDF WITH CHARTS
# =====================================================
@app.route("/export_pdf")
@login_required
def export_pdf():
    global students_df, infra_df, kpis

    if students_df is None or infra_df is None:
        return redirect("/")

    from io import BytesIO
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet

    # =====================================================
    # PREPARE STUDENT DATA FOR PDF
    # =====================================================
    students_pdf = students_df.copy()
    students_pdf.columns = students_pdf.columns.str.strip().str.lower()
    if "attendance %" in students_pdf.columns:
        students_pdf.rename(columns={"attendance %": "attendance"}, inplace=True)
    if "attendance_percent" in students_pdf.columns:
        students_pdf.rename(columns={"attendance_percent": "attendance"}, inplace=True)
    if "improvement" not in students_pdf.columns:
        if "skill_score_after" in students_pdf.columns and "skill_score_before" in students_pdf.columns:
            students_pdf["improvement"] = students_pdf["skill_score_after"] - students_pdf["skill_score_before"]
    if "attendance" not in students_pdf.columns:
        students_pdf["attendance"] = ""

    import pandas as pd
    
    # =====================================================
    # INFRASTRUCTURE SUMMARY (FOR TABLE)
    # =====================================================
    unit_gaps = {}
    infra_data = []
    for _, row in infra_df.iterrows():
        unit = row.get("unit_name", "")
        required = float(row.get("total_required_cost", 0) if pd.notna(row.get("total_required_cost")) else 0)
        received = float(row.get("amount_received", 0) if pd.notna(row.get("amount_received")) else 0)
        if unit not in unit_gaps:
            unit_gaps[unit] = required
        unit_gaps[unit] -= received
        date_rec = row.get("date_fund_received", "")
        if pd.notna(date_rec):
            try:
                date_rec = pd.to_datetime(date_rec).strftime('%d-%m-%Y')
            except Exception:
                date_rec = str(date_rec).split(' ')[0]
        else:
            date_rec = ""
        infra_data.append([unit, f"Rs.{required}", f"Rs.{received}", f"Rs.{unit_gaps[unit]}", date_rec])

    infra_grouped = infra_df.groupby("unit_name").agg(total_required_cost=("total_required_cost", "max"), total_received=("amount_received", "sum")).reset_index()
    infra_grouped["gap"] = infra_grouped["total_required_cost"] - infra_grouped["total_received"]

    # =====================================================
    # GENERATE CHARTS
    # =====================================================
    therapy_labels = list(kpis.get("therapy_wise_improvement", {}).keys())
    therapy_values = list(kpis.get("therapy_wise_improvement", {}).values())
    plt.figure(figsize=(6, 3))
    plt.bar(therapy_labels, therapy_values)
    plt.xticks(rotation=45)
    plt.tight_layout()
    therapy_chart_path = "/tmp/therapy_chart.png"
    plt.savefig(therapy_chart_path)
    plt.close()

    plt.figure(figsize=(6, 3))
    plt.bar(infra_grouped["unit_name"], infra_grouped["gap"])
    ax = plt.gca()
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f'Rs.{int(x):,}'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    infra_chart_path = "/tmp/infra_chart.png"
    plt.savefig(infra_chart_path)
    plt.close()

    # =====================================================
    # BUILD PDF USING REPORTLAB
    # =====================================================
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    elements.append(Paragraph("CSR Project Report", styles['Title']))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d %B %Y')}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # KPI Summary
    elements.append(Paragraph("Executive Summary", styles['Heading2']))
    kpi_text = f"Total Students: {kpis.get('total_students', 0)} | Funding Coverage: {kpis.get('funding_coverage_percent', 0)}%"
    elements.append(Paragraph(kpi_text, styles['Normal']))
    elements.append(Spacer(1, 12))

    # Charts
    elements.append(Paragraph("Therapy Wise Improvement", styles['Heading2']))
    elements.append(RLImage(therapy_chart_path, width=400, height=200))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("Infrastructure Gap Required", styles['Heading2']))
    elements.append(RLImage(infra_chart_path, width=400, height=200))
    elements.append(Spacer(1, 12))

    # Infrastructure Table
    elements.append(Paragraph("Infrastructure Funding Breakdown", styles['Heading2']))
    infra_table_data = [["Unit Name", "Required", "Received", "Gap", "Date"]] + infra_data
    t = Table(infra_table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(t)

    doc.build(elements)
    
    pdf_out = buffer.getvalue()
    buffer.close()

    response = make_response(pdf_out)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=CSR_Report.pdf"

    return response
# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)