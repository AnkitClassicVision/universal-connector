# Google: your own Desktop OAuth client, step by step

Use this when the door signs in to Gmail, Calendar or Drive with OAuth and needs an OAuth client of your own. The person does every step in their own browser; the agent only reads these steps out and waits. Screen names drift: where a step says "check the vendor docs", look at Google's current help for that screen.

## Before you start

- Use the Google account the connection is for (work or personal). Keep work and personal as separate connections, each with its own client.
- You need nothing paid. A Google Cloud project for this is free.

## Steps

1. **Make your own project.** In the Google Cloud console, create a new project just for the door (for example "my-door"). Do not reuse a project that runs anything else.
2. **Turn on the APIs you plan to use.** In "APIs and services", enable only those the plan needs: Gmail API, Google Calendar API, Google Drive API. Each one you leave off is one less thing a leaked sign-in can reach.
3. **Set up the consent screen.** In the OAuth consent screen (or "Google Auth Platform", check the vendor docs):
   - **Workspace account, inside your own organisation:** choose **Internal**. Only accounts in your organisation can sign in, and sign-ins do not expire after 7 days.
   - **Personal Gmail account, or an outside account:** choose **External** and leave the app in **Testing**.
   Give it a plain name, your own support email, and no logo (a logo can start a review).
4. **Add yourself as a test user** (External only). Under test users, add the exact account that will sign in. In Testing, only listed test users can sign in.
5. **Add scopes, the narrowest that fit the plan's green and yellow tools.** For example read-only scopes for mail, calendar and files, plus the draft scope only if the plan has a yellow draft tool. Note: Google's draft scope also allows sending, so the door's tiers are what keep sending off.
6. **Create the client.** In Credentials, create an OAuth client ID of type **Desktop app**. Name it after the door.
7. **Download the client file** (a JSON file) and put it where the plan says the door reads it, for example the door's state folder. Then make it readable only by you: `chmod 600 <the file>`. The agent never opens it. Google treats a Desktop client's secret as not confidential, but it still identifies your app: keep it private and never commit it.
8. **Sign in once, fresh, through the door's own login command** (stage `04-door`). Your browser opens Google's page; approve only the scopes listed. The door keeps the sign-in; you never copy a code or token anywhere.
9. **Smoke-test it**: `tools/smoke_connection.py ... --auth-kind oauth --whoami-tool <the door's profile read>` shows "signed in as <your account>".

## The 7-day Testing caveat

With an **External** app in **Testing**, Google ends the sign-in (the refresh token) after **7 days**. Until you change that, the connection stops working each week and you sign in again through the door (step 8). Ways out:

- **Workspace:** use **Internal** (step 3). No 7-day limit.
- **Personal account:** publish the app ("In production"). With sensitive or restricted scopes, Google may ask for verification first; check the vendor docs. Until then, plan a weekly sign-in and put it in the owner sheet.

## If it goes wrong

- "Access blocked" or "app not verified": the signing-in account is not a test user (step 4), or the app is Internal and the account is outside the organisation.
- "redirect_uri_mismatch": the client is not a Desktop app (step 6).
- The connection stops after a week: the 7-day Testing caveat above.
- Paging cursors: Google's list results carry `nextPageToken`; the door must drop them, or the smoke test fails on them.
