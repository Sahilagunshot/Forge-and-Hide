# Forge & Hide deployment

## Automatic PythonAnywhere deployment

The PythonAnywhere scheduled task can check `origin/main` and deploy new commits
without putting an API token in GitHub or in this repository. It only fast-forwards
a clean `main` checkout. It leaves the live database and ignored uploads in place,
installs requirements when `requirements.txt` changes, applies committed database
migrations, and touches the configured WSGI file to reload the app.

This deploys **committed changes pushed to `main`**. Unsaved files, other local
folders, and untracked/ignored files are not included. New product or banner data
entered in a local database, and new files under `static/uploads/`, are not
synced by Git. Add or update that content on the live site separately; never
replace the live database with a local copy because it contains production data.

### One-time setup

1. Push this deployment script to GitHub, then pull it into
   `/home/ForgenHide/Forge-and-Hide` on PythonAnywhere.
2. In the PythonAnywhere Web tab, set both **Source code** and **Working
   directory** to `/home/ForgenHide/Forge-and-Hide`.
3. Open the WSGI configuration file link on that tab and note its exact file
   path. Do not replace the WSGI file; the deployment task only touches it to
   request a reload.
4. In PythonAnywhere **Tasks**, create a scheduled task at the shortest interval
   available on the account. Use this command, replacing the WSGI path with the
   exact path from the Web tab:

   ```bash
   source /home/ForgenHide/.virtualenvs/forge-env/bin/activate && \
     bash /home/ForgenHide/Forge-and-Hide/scripts/deploy_pythonanywhere.sh \
     /var/www/<exact_wsgi_file>
   ```

The script stops safely if the branch is not `main`, the checkout has local
changes, the update is not a fast-forward, the virtualenv is not active, or the
WSGI path is invalid. Check the scheduled task's output for failures. If a
deployment is blocked by local changes, inspect them before resolving anything;
do not use `git reset --hard`.

Model changes need a committed migration under `migrations/versions/`; the
scheduled task applies committed migrations with `flask db upgrade`.