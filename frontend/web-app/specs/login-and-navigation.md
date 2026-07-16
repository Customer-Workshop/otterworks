# Login and Navigation Test Plan

## Application Overview

OtterWorks is a collaborative document and file management application. Guest
users can view the public landing page, sign in, or create an account. Protected
areas require authentication and should present the login form or redirect an
unauthenticated visitor to `/login`.

## Login Page

**Seed:** `e2e/seed.spec.ts`

### 1. Login form fields and branding are visible

**Starting state:** Open a fresh browser context as an unauthenticated user.

**Steps:**

1. Navigate to `/login`.
2. Verify the Email field is visible.
3. Verify the Password field is visible.
4. Verify the Sign in button is visible.
5. Verify the OtterWorks branding is visible.
6. Verify the text "Sign in to your account" is visible.

**Expected result:** The branded login form is ready for an unauthenticated
user.

### 2. Login validation rejects an empty email

**Starting state:** Open a fresh browser context as an unauthenticated user.

**Steps:**

1. Navigate to `/login`.
2. Enter a password in the Password field.
3. Activate the Sign in button.
4. Verify "Please enter a valid email" is visible.

**Expected result:** The form remains on the login page and explains that the
email is invalid.

### 3. Login page links to registration

**Starting state:** Open a fresh browser context as an unauthenticated user.

**Steps:**

1. Navigate to `/login`.
2. Verify the "Create one" link is visible.
3. Activate the "Create one" link.
4. Verify the browser URL is `/register`.

**Expected result:** A visitor can navigate from login to account registration.

### 4. Invalid credentials show an error

**Starting state:** Open a fresh browser context as an unauthenticated user.

**Steps:**

1. Navigate to `/login`.
2. Enter `nonexistent@test.com` in the Email field.
3. Enter `WrongPassword123` in the Password field.
4. Activate the Sign in button.
5. Verify "Invalid email or password" is visible.

**Expected result:** Invalid credentials are rejected with a clear error.

## Public Navigation

**Seed:** `e2e/seed.spec.ts`

### 5. Dashboard requires authentication

**Starting state:** Open a fresh browser context with no auth tokens.

**Steps:**

1. Navigate to `/dashboard`.
2. Verify the Dashboard page is visible, or verify "Sign in to your account"
   is visible.

**Expected result:** An unauthenticated visitor cannot access the dashboard
without encountering the login form or a redirect to `/login`.

### 6. Documents requires authentication

**Starting state:** Open a fresh browser context with no auth tokens.

**Steps:**

1. Navigate to `/documents`.
2. Verify the Documents page is visible, or verify "Sign in to your account"
   is visible.

**Expected result:** An unauthenticated visitor cannot access documents without
encountering the login form or a redirect to `/login`.

### 7. Files requires authentication

**Starting state:** Open a fresh browser context with no auth tokens.

**Steps:**

1. Navigate to `/files`.
2. Verify the Files or My Files page is visible, or verify "Sign in to your
   account" is visible.

**Expected result:** An unauthenticated visitor cannot access files without
encountering the login form or a redirect to `/login`.
