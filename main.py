import sqlite3
from datetime import datetime
from uuid import uuid4

from core import database as database_store
from core import profiles as profile_store
from core.config import (
    APP_NAME,
    APP_VERSION,
    BASE_DIR,
    CV_DIR,
    DATA_DIR,
    DATABASE_FILE,
    PROFILE_FILE,
)
from core.cv import (
    add_cv_section,
    add_work_experience_section,
    build_cv_content,
    generate_cv_pdf,
    save_cv_bundle,
)
from core.database import get_database_connection


# ============================================================
# KAZIMSAADA AI
# Career Readiness Assistant for Kenyan Job Seekers
# ============================================================


# ============================================================
# 1. APPLICATION INTRODUCTION
# ============================================================

def display_header():
    print("\n" + "=" * 55)
    print(f"              {APP_NAME}")
    print("          Career Readiness Assistant")
    print("=" * 55)
    print("  Supporting your journey into the world of work.")
    print(f"  Version: {APP_VERSION}")
    print("=" * 55)


def welcome():
    display_header()

    print("\nWelcome to KaziMsaada AI!")
    print("Your journey towards career readiness starts here.")

    print("\nThis assistant is being developed to help you:")
    print("- Build a professional CV")
    print("- Prepare for job interviews")
    print("- Identify your skills")
    print("- Explore career pathways")
    print("- Improve your job application skills")


# ============================================================
# 2. INPUT VALIDATION
# ============================================================

def get_required_input(prompt):
    """Ask repeatedly until the user enters a value."""

    while True:
        value = input(prompt).strip()

        if value:
            return value

        print("This field is required. Please try again.")


def get_optional_input(prompt, default="Not provided"):
    """Allow the user to leave a field blank."""

    value = input(prompt).strip()

    return value if value else default


def collect_skills():
    """Collect skills and remove duplicate entries."""

    while True:
        skills_input = input(
            "\nEnter your skills separated by commas "
            "(or press Enter to skip): "
        ).strip()

        if not skills_input:
            return []

        skills = [
            skill.strip()
            for skill in skills_input.split(",")
            if skill.strip()
        ]

        unique_skills = []
        seen = set()

        for skill in skills:
            if skill.casefold() not in seen:
                unique_skills.append(skill)
                seen.add(skill.casefold())

        if unique_skills:
            return unique_skills

        print("Please enter valid skills or press Enter to skip.")


# ============================================================
# 3. CAREER SUPPORT FEATURES
# ============================================================

def select_cv_profile():
    """Allow a job seeker to select a saved profile for CV creation."""

    profiles = load_profiles()

    if profiles is None:
        return None

    if not profiles:
        print("\nNo saved profiles found.")
        print("Please create a career profile first.")
        return None

    print("\n" + "=" * 55)
    print("             SELECT YOUR CAREER PROFILE")
    print("=" * 55)

    for number, profile in enumerate(profiles, start=1):
        print(
            f"{number}. {profile['name']} "
            f"| {profile['career_interest']} "
            f"| ID: {profile['profile_id'][:8]}"
        )

    while True:
        choice = input(
            "\nSelect a profile number (or 0 to cancel): "
        ).strip()

        if choice == "0":
            print("CV creation cancelled.")
            return None

        try:
            number = int(choice)

            if 1 <= number <= len(profiles):
                return profiles[number - 1]

        except ValueError:
            pass

        print("Invalid selection. Please try again.")


def collect_cv_list(prompt):
    """Collect multiple CV entries separated by semicolons."""

    value = input(prompt).strip()

    if not value:
        return []

    return [
        item.strip()
        for item in value.split(";")
        if item.strip()
    ]


def collect_work_experience():
    """Collect work experience as structured records."""

    experiences = []

    print("\nWORK EXPERIENCE")
    print("You can add multiple positions.")
    print("If you have no work experience, enter 'no'.")

    choice = input(
        "\nWould you like to add work experience? (yes/no): "
    ).strip().casefold()

    while choice in ("yes", "y"):

        print("\nEnter the details of this position.")

        organisation = get_required_input(
            "Organisation or company name: "
        )

        job_title = get_required_input(
            "Job title or position: "
        )

        location = get_optional_input(
            "Job location (optional): ",
            ""
        )

        start_date = get_optional_input(
            "Start date (e.g. January 2024): ",
            ""
        )

        end_date = get_optional_input(
            "End date (e.g. December 2024 or Present): ",
            ""
        )

        responsibilities = collect_cv_list(
            "Responsibilities and achievements "
            "(separate with semicolons): "
        )

        experiences.append({
            "organisation": organisation,
            "job_title": job_title,
            "location": location,
            "start_date": start_date,
            "end_date": end_date,
            "responsibilities": responsibilities
        })

        choice = input(
            "\nWould you like to add another position? (yes/no): "
        ).strip().casefold()

    return experiences


def choose_cv_template():
    """Let the applicant choose a CV layout."""

    templates = {
        "1": ("classic", "Classic Professional",
              "A clean, traditional, single-column layout."),
        "2": ("modern", "Modern Professional",
              "A contemporary layout with a strong colour accent."),
        "3": ("graduate", "Graduate and Early-Career",
              "A layout that highlights education, skills and projects.")
    }

    print("\n" + "=" * 60)
    print("                 CHOOSE YOUR CV TEMPLATE")
    print("=" * 60)

    for number, (_, name, description) in templates.items():
        print(f"\n{number}. {name}")
        print(f"   {description}")

    while True:
        choice = input("\nChoose a template (1-3): ").strip()

        if choice in templates:
            template_id, name, _ = templates[choice]
            print(f"\nSelected template: {name}")
            return template_id, name

        print("Invalid selection. Please choose 1, 2 or 3.")


def improve_cv():
    """Create a professional CV using a saved career profile."""

    print("\n" + "=" * 55)
    print("             CV CREATION & IMPROVEMENT")
    print("=" * 55)

    profile = select_cv_profile()

    if profile is None:
        return

    print("\nSelected career profile:")
    display_profile(profile)

    print("\nPlease provide additional CV information.")

    phone = get_required_input("\nPhone number: ")
    email = get_required_input("Email address: ")

    target_role = get_required_input(
        "What job position are you applying for? "
    )

    summary = get_optional_input(
        "Write a short professional summary relevant to "
        f"{target_role} (optional): ",
        ""
    )

    education = collect_cv_list(
        "Additional education details (separate with semicolons): "
    )

    experience = collect_work_experience()

    projects = collect_cv_list(
        "Projects or practical experience (optional): "
    )

    volunteering = collect_cv_list(
        "Volunteering activities (optional): "
    )

    certifications = collect_cv_list(
        "Certifications or training (optional): "
    )

    languages = collect_cv_list(
        "Languages (optional): "
    )

    referees = collect_cv_list(
        "Referees (name, position, organisation, "
        "phone number, email): "
    )

    if not referees:
        referee_choice = input(
            "Would you like to state 'Referees available "
            "upon request'? (yes/no): "
        ).strip().casefold()

        if referee_choice in ("yes", "y"):
            referees = ["Available upon request"]

    cv_data = {
        "phone": phone,
        "email": email,
        "target_role": target_role,
        "summary": summary,
        "education": education,
        "experience": experience,
        "projects": projects,
        "volunteering": volunteering,
        "certifications": certifications,
        "languages": languages,
        "referees": referees,
    }

    cv_content = build_cv_content(profile, cv_data)

    # Preview the CV.
    print("\n" + "=" * 60)
    print("                  CV PREVIEW")
    print("=" * 60)

    print(cv_content)

    confirm = input(
        "\nWould you like to save this CV? (yes/no): "
    ).strip().casefold()

    if confirm not in ("yes", "y"):
        print("\nCV was not saved.")
        return

    template_id, template_name = choose_cv_template()

    try:
        saved_cv = save_cv_bundle(
            profile,
            cv_data,
            template_id,
            cv_dir=CV_DIR,
        )

        txt_path = saved_cv["txt_path"]
        pdf_path = saved_cv["pdf_path"]

        print("\nYour CV has been generated successfully!")
        print(f"\nText CV: {txt_path.resolve()}")
        print(f"PDF CV:  {pdf_path.resolve()}")
        print(f"Template: {template_name}")

    except OSError as error:
        print(f"\nFile storage error: {error}")

    except Exception as error:
        print(f"\nPDF generation error: {error}")
        print("Your text CV may still be available as a backup.")


def interview_prep():
    print("\n" + "=" * 55)
    print("               INTERVIEW PREPARATION")
    print("=" * 55)

    print("This feature will help you:")
    print("- Practise common interview questions")
    print("- Prepare answers using your own experience")
    print("- Improve your communication")
    print("- Build confidence before interviews")

    print("\nStatus: This feature is under development.")


def skills_assessment():
    print("\n" + "=" * 55)
    print("                  SKILLS ASSESSMENT")
    print("=" * 55)

    print("This feature will help you:")
    print("- Identify your existing skills")
    print("- Recognise transferable skills")
    print("- Identify areas for improvement")
    print("- Explore relevant learning opportunities")

    print("\nStatus: This feature is under development.")


def career_guidance():
    print("\n" + "=" * 55)
    print("                   CAREER GUIDANCE")
    print("=" * 55)

    print("This feature will help you:")
    print("- Explore career paths")
    print("- Understand different industries")
    print("- Connect your skills to career opportunities")
    print("- Identify useful professional development steps")

    print("\nStatus: This feature is under development.")


def job_tips():
    print("\n" + "=" * 55)
    print("               JOB APPLICATION TIPS")
    print("=" * 55)

    tips = [
        "Tailor your CV to each vacancy.",
        "Research the organisation before applying.",
        "Follow application instructions carefully.",
        "Use clear and professional language.",
        "Highlight projects, internships and volunteering.",
        "Prepare examples that demonstrate your skills.",
        "Keep track of jobs you have applied for.",
        "Never pay someone for a promise of employment."
    ]

    for number, tip in enumerate(tips, start=1):
        print(f"{number}. {tip}")


# ============================================================
# 4. DATABASE CONNECTION MANAGEMENT
# ============================================================

# get_database_connection is imported from core.database so the CLI and the
# Streamlit application always use the same connection behaviour and path.


# ============================================================
# 5. DATABASE INITIALISATION
# ============================================================

def initialize_database():
    """Create the required database tables."""

    try:
        database_store.initialize_database()

    except sqlite3.Error as error:
        print(f"\nDatabase initialisation failed: {error}")
        raise

    print("\nDatabase initialised successfully.")

    migrate_json_profiles()


# ============================================================
# 6. MIGRATE EXISTING JSON PROFILES INTO SQLITE
# ============================================================

def _report_migration(result):
    """Print the outcome of the shared JSON migration."""

    status = result.get("status")

    if status == "no_source":
        print("No existing JSON profiles to migrate.")

    elif status == "already_completed":
        print("Existing JSON migration already completed.")

    elif status == "invalid_source":
        print("JSON migration skipped: invalid profile structure.")

    elif status == "source_error":
        print(
            "Could not read the JSON migration file: "
            f"{result.get('error')}"
        )

    elif status == "database_error":
        print(f"Database migration failed: {result.get('error')}")

    elif status == "imported":
        print(
            f"JSON migration completed. "
            f"{result.get('imported', 0)} new profile(s) imported."
        )
        print("Your original JSON backup has been preserved.")


def migrate_json_profiles():
    """
    Import existing JSON profiles into SQLite once.

    The original JSON file is not deleted or modified.
    """

    _report_migration(database_store.migrate_json_profiles())


# ============================================================
# 7. PROFILE DATA OPERATIONS
# ============================================================

def load_profiles():
    """Retrieve all job seeker profiles from SQLite."""

    print(f"\nReading database: {DATABASE_FILE.resolve()}")

    try:
        return profile_store.load_profiles()

    except sqlite3.Error as error:
        print(f"Could not retrieve profiles: {error}")
        return None


def save_profile(job_seeker):
    """Save a profile and verify that SQLite stored it."""

    try:
        saved_profile = profile_store.save_profile_record(job_seeker)

    except sqlite3.IntegrityError as error:
        print(f"\nProfile could not be saved: {error}")
        return False

    except sqlite3.Error as error:
        print(f"\nDatabase error while saving: {error}")
        return False

    except profile_store.ProfileNotFoundError:
        print("\nERROR: Profile was not found after saving.")
        return False

    print("\nProfile saved and verified successfully!")
    print(f"Name: {saved_profile['name']}")
    print(f"Profile ID: {saved_profile['profile_id']}")
    print(f"Database location: {DATABASE_FILE.resolve()}")

    return True


def update_profile_record(profile):
    """Update an existing profile in SQLite."""

    try:
        return profile_store.update_profile_record(profile)

    except sqlite3.Error as error:
        print(f"Could not update the profile: {error}")
        return False


def delete_profile_record(profile_id):
    """Delete one profile from SQLite using its unique ID."""

    try:
        return profile_store.delete_profile_record(profile_id)

    except sqlite3.Error as error:
        print(f"Could not delete the profile: {error}")
        return False


# ============================================================
# 8. CREATE A JOB SEEKER PROFILE
# ============================================================

def create_profile():

    print("\n" + "=" * 55)
    print("                CREATE CAREER PROFILE")
    print("=" * 55)

    print("Tell us about yourself.")
    print("You can enter 'No formal experience yet' if applicable.")

    name = get_required_input("\nFull name: ")

    education = get_required_input(
        "Highest education level: "
    )

    location = get_required_input(
        "Town or county: "
    )

    experience = get_optional_input(
        "Work experience (press Enter if you have none): ",
        "No formal work experience yet"
    )

    career_interest = get_required_input(
        "Career or industry of interest: "
    )

    skills = collect_skills()

    job_seeker = {
        "profile_id": str(uuid4()),
        "created_at": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "name": name,
        "education": education,
        "location": location,
        "experience": experience,
        "career_interest": career_interest,
        "skills": skills
    }

    display_profile(job_seeker)

    confirm = input(
        "\nWould you like to save this profile? (yes/no): "
    ).strip().casefold()

    if confirm in ("yes", "y"):
        save_profile(job_seeker)

    else:
        print("\nYour profile was not saved.")


# ============================================================
# 9. DISPLAY A JOB SEEKER PROFILE
# ============================================================

def display_profile(profile):

    print("\n" + "=" * 55)
    print("                 CAREER PROFILE")
    print("=" * 55)

    print(f"Name: {profile.get('name', 'Not provided')}")
    print(f"Education: {profile.get('education', 'Not provided')}")
    print(f"Location: {profile.get('location', 'Not provided')}")
    print(f"Experience: {profile.get('experience', 'Not provided')}")
    print(
        f"Career interest: "
        f"{profile.get('career_interest', 'Not provided')}"
    )

    print("\nSkills:")

    skills = profile.get("skills", [])

    if isinstance(skills, list) and skills:
        for skill in skills:
            print(f"- {skill}")
    else:
        print("No skills added yet.")

    print("=" * 55)


# ============================================================
# 10. VIEW SAVED PROFILES
# ============================================================

def view_profiles():

    print("\n" + "=" * 55)
    print("              SAVED CAREER PROFILES")
    print("=" * 55)

    profiles = load_profiles()

    if profiles is None:
        return

    if not profiles:
        print("\nNo profiles have been saved yet.")
        return

    print(f"\nTotal profiles: {len(profiles)}")

    for number, profile in enumerate(profiles, start=1):

        print(f"\nPROFILE {number}")
        display_profile(profile)

        print(
            f"Profile ID: "
            f"{profile.get('profile_id', 'Unavailable')}"
        )

        print(
            f"Created: "
            f"{profile.get('created_at', 'Unavailable')}"
        )

        print(
            f"Last updated: "
            f"{profile.get('updated_at') or 'Not updated'}"
        )


# ============================================================
# 11. SEARCH PROFILES
# ============================================================

def search_profiles():

    print("\n" + "=" * 55)
    print("                  SEARCH PROFILES")
    print("=" * 55)

    profiles = load_profiles()

    if profiles is None:
        return []

    if not profiles:
        print("There are no saved profiles to search.")
        return []

    search_term = input(
        "\nEnter a name or profile ID: "
    ).strip().casefold()

    if not search_term:
        print("Please enter a search term.")
        return []

    matches = []

    for profile in profiles:

        name = str(profile.get("name", "")).casefold()
        profile_id = str(profile.get("profile_id", "")).casefold()

        if search_term in name or search_term == profile_id:
            matches.append(profile)

    if not matches:
        print("\nNo matching profiles were found.")
        return []

    print(f"\nFound {len(matches)} matching profile(s).")

    for number, profile in enumerate(matches, start=1):

        print(f"\nMATCH {number}")
        display_profile(profile)

        print(
            f"Profile ID: "
            f"{profile.get('profile_id', 'Unavailable')}"
        )

    return matches


# ============================================================
# 12. SELECT A PROFILE
# ============================================================

def select_profile(profiles):
    """Allow the user to select one search result."""

    if not profiles:
        return None

    if len(profiles) == 1:
        return profiles[0]

    while True:

        selection = input(
            "\nEnter the number of the profile to select "
            "(or 0 to cancel): "
        ).strip()

        if selection == "0":
            print("Selection cancelled.")
            return None

        try:
            number = int(selection)

            if 1 <= number <= len(profiles):
                return profiles[number - 1]

        except ValueError:
            pass

        print(
            f"Please enter a number between 1 and {len(profiles)}, "
            "or 0 to cancel."
        )


# ============================================================
# 13. UPDATE A JOB SEEKER PROFILE
# ============================================================

def update_profile():

    matches = search_profiles()
    selected = select_profile(matches)

    if selected is None:
        return

    # Work on a separate copy until the user confirms.
    profile = selected.copy()
    profile["skills"] = list(selected.get("skills", []))

    print("\n" + "=" * 55)
    print("                  UPDATE PROFILE")
    print("=" * 55)

    print("Press Enter to keep the current value.")

    fields = {
        "name": "Full name",
        "education": "Education",
        "location": "Town or county",
        "experience": "Work experience",
        "career_interest": "Career interest"
    }

    for field, label in fields.items():

        current_value = str(profile.get(field, ""))

        new_value = input(
            f"\n{label} [{current_value}]: "
        ).strip()

        if new_value:
            profile[field] = new_value

    current_skills = profile.get("skills", [])

    print(
        "\nCurrent skills: "
        + (", ".join(current_skills) if current_skills else "None")
    )

    skills_input = input(
        "Enter replacement skills, press Enter to keep, "
        "or type 'clear' to remove them: "
    ).strip()

    if skills_input.casefold() == "clear":

        profile["skills"] = []

    elif skills_input:

        new_skills = [
            skill.strip()
            for skill in skills_input.split(",")
            if skill.strip()
        ]

        unique_skills = []
        seen = set()

        for skill in new_skills:

            if skill.casefold() not in seen:
                unique_skills.append(skill)
                seen.add(skill.casefold())

        if unique_skills:
            profile["skills"] = unique_skills

    profile["updated_at"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    print("\nReview the updated profile:")
    display_profile(profile)

    confirm = input(
        "\nSave these changes? (yes/no): "
    ).strip().casefold()

    if confirm in ("yes", "y"):

        if update_profile_record(profile):
            print("\nProfile updated successfully!")
        else:
            print("\nThe profile could not be updated.")

    else:
        print("\nChanges cancelled. No changes were saved.")


# ============================================================
# 14. DELETE A JOB SEEKER PROFILE
# ============================================================

def delete_profile():

    matches = search_profiles()
    selected = select_profile(matches)

    if selected is None:
        return

    profile_id = selected.get("profile_id")

    if not profile_id:
        print("This profile has no unique ID and cannot be deleted.")
        return

    print("\nYou are about to delete this profile:")
    display_profile(selected)

    print("\nWARNING: This action cannot be undone.")

    confirmation = input(
        "Type DELETE to permanently remove this profile: "
    ).strip()

    if confirmation == "DELETE":

        if delete_profile_record(profile_id):
            print("\nProfile deleted successfully.")
        else:
            print("\nThe profile could not be deleted.")

    else:
        print("\nDeletion cancelled. No changes were made.")


# ============================================================
# 15. MAIN APPLICATION MENU
# ============================================================

def main():

    # Prepare the database before showing the application.
    initialize_database()

    welcome()

    while True:

        print("\n" + "=" * 55)
        print("                    MAIN MENU")
        print("=" * 55)

        print("1. CV Creation and Improvement")
        print("2. Interview Preparation")
        print("3. Skills Assessment")
        print("4. Career Guidance")
        print("5. Job Application Tips")
        print("6. Create Career Profile")
        print("7. View Saved Profiles")
        print("8. Search Profiles")
        print("9. Update Profile")
        print("10. Delete Profile")
        print("11. Exit")

        choice = input(
            "\nSelect an option (1-11): "
        ).strip()

        if choice == "1":
            improve_cv()

        elif choice == "2":
            interview_prep()

        elif choice == "3":
            skills_assessment()

        elif choice == "4":
            career_guidance()

        elif choice == "5":
            job_tips()

        elif choice == "6":
            create_profile()

        elif choice == "7":
            view_profiles()

        elif choice == "8":
            search_profiles()

        elif choice == "9":
            update_profile()

        elif choice == "10":
            delete_profile()

        elif choice == "11":

            print("\nThank you for using KaziMsaada AI.")
            print("Keep learning. Keep growing. Keep moving forward.")
            print("\nGoodbye!")

            break

        else:
            print("\nInvalid selection.")
            print("Please enter a number between 1 and 11.")


# ============================================================
# 16. APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
