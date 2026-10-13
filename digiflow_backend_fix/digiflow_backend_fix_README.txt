DigiFlow backend/storage fix

Files included:
- app/main.py       FastAPI backend with storage/product/run/task/review/audit APIs
- app/storage.py    SQLite persistence in E:\\digiflow_starter\\data\\digiflow.sqlite3
- app/static/app.js Clickable dashboard controls + live backend status/modals

Apply:
1. Back up app/main.py and app/dashboard.html.
2. Copy the included files into the matching app/ locations.
3. Add this line before </body> in app/dashboard.html if it is not already there:
   <script src="/static/app.js"></script>
4. Start with: python run.py

The backend does NOT store passwords. Browser login remains manual.
The product collector/scraper itself is not included in this patch; this patch creates the persistent registry, review queue, task/run records, audit trail, and API layer that the collector will use.
