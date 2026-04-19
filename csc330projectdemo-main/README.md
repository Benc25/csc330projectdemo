# Open Kitchen Demo

This is a cleaned demo build:
- working create/view recipe flow
- working SQLite database with demo records
- search by title, ingredient, dietary tag, and allergen
- ingredient scaling on the create page and recipe detail page
- cleaner, more polished styling

## Run steps (Windows PowerShell)

### 1) Go into the project folder
```powershell
cd "PATH\TO\csc330projectdemo"
```

### 2) Install dependencies
```powershell
py -m pip install -r requirements.txt
```

### 3) Start the app
```powershell
py main.py
```

### 4) Open in browser
```text
http://127.0.0.1:5000
```

## Main demo pages
- `/` dashboard
- `/recipe/create` create recipe
- `/recipe/<id>` recipe detail
- `/search?q=pasta` search results example

## Notes
- CSRF is disabled for easy classroom demo use.
- The app uses the included SQLite database at `app/recipe.db`.
- The demo uses user ID 1 as the placeholder creator when saving new recipes.
