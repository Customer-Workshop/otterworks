Feature: Authentication
  As a user
  I want to register and log in to OtterWorks
  So that I can access my documents and files

  Scenario: Registration form renders correctly
    Given I am on the registration page
    Then I should see the text "Create your account"
    And I should see a "Full name" input field
    And I should see an "Email" input field
    And I should see a "Password" input field
    And I should see a "Confirm password" input field
    And I should see a "Create account" button

  Scenario: Registration rejects short name
    Given I am on the registration page
    When I fill in "Full name" with "A"
    And I fill in "Email" with "test@example.com"
    And I fill in "Password" with "Passw0rd!23"
    And I fill in "Confirm password" with "Passw0rd!23"
    And I click the "Create account" button
    Then I should see the text "Name must be at least 2 characters"

  Scenario: Registration rejects invalid email
    Given I am on the registration page
    When I fill in "Full name" with "Test User"
    And I fill in "Email" with "not-an-email"
    And I fill in "Password" with "Passw0rd!23"
    And I fill in "Confirm password" with "Passw0rd!23"
    And I click the "Create account" button
    Then the URL should contain "/register"

  Scenario: Registration rejects mismatched passwords
    Given I am on the registration page
    When I fill in "Full name" with "Test User"
    And I fill in "Email" with "test@example.com"
    And I fill in "Password" with "Passw0rd!23"
    And I fill in "Confirm password" with "DifferentPass1!"
    And I click the "Create account" button
    Then I should see the text "Passwords do not match"

  Scenario: Login form renders correctly
    Given I am on the login page
    Then I should see the text "Sign in to your account"
    And I should see an "Email" input field
    And I should see a "Password" input field
    And I should see a "Sign in" button

  Scenario: Login rejects empty email
    Given I am on the login page
    When I fill in "Password" with "somepassword"
    And I click the "Sign in" button
    Then I should see the text "Please enter a valid email"

  Scenario: Login rejects empty password
    Given I am on the login page
    When I fill in "Email" with "user@test.com"
    And I click the "Sign in" button
    Then I should see the text "Password is required"

  Scenario: Login page links to registration
    Given I am on the login page
    Then I should see a link "Create one"
    When I click the link "Create one"
    Then the URL should contain "/register"

  Scenario: Registration page links to login
    Given I am on the registration page
    Then I should see a link "Sign in"
    When I click the link "Sign in"
    Then the URL should contain "/login"
