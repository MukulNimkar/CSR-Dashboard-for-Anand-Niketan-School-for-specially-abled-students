import pandas as pd


# =====================================================
# READ EXCEL FILE
# =====================================================
def process_excel(file_path):

    students_df = pd.read_excel(file_path, sheet_name="students")
    infra_df = pd.read_excel(file_path, sheet_name="infrastructure")

    return students_df, infra_df


# =====================================================
# CALCULATE KPIs
# =====================================================
def calculate_kpis(students_df, infra_df):

    # -------------------------
    # BASIC STUDENT KPIs
    # -------------------------
    total_students = len(students_df)

    avg_attendance = round(
        students_df["attendance"].mean(), 1
    ) if "attendance" in students_df.columns else 0

    # -------------------------
    # IMPROVEMENT
    # -------------------------
    if "skill_score_after" in students_df.columns and "skill_score_before" in students_df.columns:
        students_df["improvement"] = (
            students_df["skill_score_after"]
            - students_df["skill_score_before"]
        )
        avg_improvement = round(students_df["improvement"].mean(), 1)
        total_improvement = students_df["improvement"].sum()
    else:
        avg_improvement = 0
        total_improvement = 0

    # -------------------------
    # CLEAN NUMERIC COLUMNS
    # -------------------------
    students_df["monthly_cost"] = students_df.get("monthly_cost", 0)
    students_df["sponsorship_amount"] = students_df.get("sponsorship_amount", 0)

    students_df["monthly_cost"] = students_df["monthly_cost"].fillna(0)
    students_df["sponsorship_amount"] = students_df["sponsorship_amount"].fillna(0)

    infra_df["total_required_cost"] = infra_df.get("total_required_cost", 0)
    infra_df["amount_received"] = infra_df.get("amount_received", 0)

    infra_df["total_required_cost"] = infra_df["total_required_cost"].fillna(0)
    infra_df["amount_received"] = infra_df["amount_received"].fillna(0)

    # -------------------------
    # FUNDING CALCULATIONS
    # -------------------------
    total_student_cost = students_df["monthly_cost"].sum()
    total_student_received = students_df["sponsorship_amount"].sum()

    student_funding_gap = total_student_cost - total_student_received

    total_infra_required = infra_df["total_required_cost"].sum()
    total_infra_received = infra_df["amount_received"].sum()

    infrastructure_gap = total_infra_required - total_infra_received
    total_funding_gap = student_funding_gap + infrastructure_gap

    # -------------------------
    # FUNDING COVERAGE %
    # -------------------------
    if total_infra_required > 0:
        funding_coverage_percent = round(
            (total_infra_received / total_infra_required) * 100,
            1
        )
    else:
        funding_coverage_percent = 0

    # -------------------------
    # COST EFFICIENCY
    # -------------------------
    if total_students > 0:
        cost_per_student = round(total_student_cost / total_students, 0)
    else:
        cost_per_student = 0

    if total_improvement > 0:
        cost_per_improvement_point = round(
            total_student_received / total_improvement, 0
        )
    else:
        cost_per_improvement_point = 0

    # -------------------------
    # DISABILITY DISTRIBUTION
    # -------------------------
    disability_counts = (
        students_df["disability"].value_counts().to_dict()
        if "disability" in students_df.columns else {}
    )

    # -------------------------
    # THERAPY IMPACT
    # -------------------------
    therapy_wise_improvement = (
        students_df.groupby("therapy_type")["improvement"]
        .mean()
        .round(1)
        .to_dict()
        if "therapy_type" in students_df.columns and "improvement" in students_df.columns
        else {}
    )

    # -------------------------
    # TEACHER PERFORMANCE
    # -------------------------
    teacher_performance = (
        students_df.groupby("teacher")["improvement"]
        .mean()
        .round(1)
        .to_dict()
        if "teacher" in students_df.columns and "improvement" in students_df.columns
        else {}
    )

    # -------------------------
    # SPONSOR CONTRIBUTION
    # -------------------------
    sponsor_contribution = (
        infra_df.groupby("sponsor_name")["amount_received"]
        .sum()
        .to_dict()
        if "sponsor_name" in infra_df.columns
        else {}
    )

    # -------------------------
    # DISABILITY VS IMPROVEMENT
    # -------------------------
    disability_wise_improvement = (
        students_df.groupby("disability")["improvement"]
        .mean()
        .round(1)
        .to_dict()
        if "disability" in students_df.columns and "improvement" in students_df.columns
        else {}
    )

    # -------------------------
    # RETURN ALL KPIs
    # -------------------------
    return {
        "total_students": int(total_students),
        "avg_attendance": avg_attendance,
        "avg_improvement": avg_improvement,
        "student_funding_gap": int(student_funding_gap),
        "infrastructure_gap": int(infrastructure_gap),
        "total_funding_gap": int(total_funding_gap),
        "funding_coverage_percent": funding_coverage_percent,
        "cost_per_student": int(cost_per_student),
        "cost_per_improvement_point": int(cost_per_improvement_point),
        "disability_counts": disability_counts,
        "therapy_wise_improvement": therapy_wise_improvement,
        "teacher_performance": teacher_performance,
        "sponsor_contribution": sponsor_contribution,
        "disability_wise_improvement": disability_wise_improvement
    }