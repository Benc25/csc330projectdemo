# The Open Kitchen

A collaborative recipe management web app built with Flask. Users can create, fork, and share recipes with family and small community groups — keeping food traditions alive and adaptable.

## Features

- Create, edit, delete, and fork recipes
- Ingredient scaling (imperial and metric)
- Search by title, ingredient, dietary tag, or allergen
- Community ratings and comments
- Quick tips on recipe pages
- Save recipes to your profile
- Share recipes to groups and message group members
- AI recipe generation via The Pot (Anthropic API) — drag ingredients in and generate a full recipe
- Drag-and-drop recipe builder page at `/pot`
- Notification system with toast popups
- Do Not Disturb status toggle on profile
- Curator dashboard for managing users, groups, and platform data (with CSV exports)
- Background video support
- Animated background on recipe pages

## Setup

### 1. Clone the repo and enter the project folder
```bash
cd csc330projectdemo
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.flaskenv` file in the project root (it is gitignored):
```
FLASK_APP=main.py
FLASK_DEBUG=1
SQLITE_DB=recipe.db
FLASK_RUN_HOST=0.0.0.0
FLASK_RUN_PORT=8080
ANTHROPIC_API_KEY=your-anthropic-api-key-here
```

### 5. Run database migrations
```bash
flask db upgrade
```

### 6. Start the app
```bash
flask run
```

### 7. Open in browser
```
http://127.0.0.1:8080
```

## Key Pages

| Route | Description |
|---|---|
| `/` | Dashboard — popular, random, and newest recipes |
| `/recipe/create` | Create a new recipe |
| `/recipe/<id>` | Recipe detail page |
| `/pot` | Drag-and-drop AI recipe builder |
| `/search?q=pasta` | Search results |
| `/groups` | Your groups and profile stats |
| `/profile/settings` | Avatar, metric preference, notifications |
| `/curator` | Curator-only admin dashboard |

## Project Structure

```
csc330projectdemo/
├── app/
│   ├── models.py          # SQLAlchemy models
│   ├── routes.py          # All Flask routes
│   ├── forms.py           # WTForms definitions
│   ├── static/
│   │   ├── style.css      # Main stylesheet
│   │   ├── uploads/       # User-uploaded images
│   │   └── background_video.mp4
│   └── templates/
│       ├── base.html      # Base layout + Magic Pot widget
│       ├── dashboard.html
│       ├── view_recipe.html
│       ├── recipe_pot.html
│       ├── curator/
│       └── groups/
├── migrations/            # Alembic migration files
├── main.py
├── requirements.txt
└── .flaskenv              # Environment variables (gitignored)
```

## Notes

- `.flaskenv` is gitignored — never commit your API key
- The app uses SQLite stored at `app/recipe.db`
- A user with `role = 'curator'` gets access to the curator dashboard
- The Pot widget on every page persists ingredients in localStorage per session and clears on logout
