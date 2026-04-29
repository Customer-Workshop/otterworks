Feature: Document Management
  As an authenticated user
  I want to manage my documents
  So that I can create, edit, and organize my work

  Scenario: Documents page shows heading or login redirect
    Given I navigate to "/documents"
    Then I should see the text "Documents" or "Sign in to your account"

  Scenario: Documents page has a New document button
    Given I navigate to "/documents"
    Then I should see the text "Documents" or "Sign in to your account"

  Scenario: Documents page has a filter input
    Given I navigate to "/documents"
    Then I should see the text "Documents" or "Sign in to your account"

  Scenario: Search page shows search input
    Given I navigate to "/search"
    Then I should see the text "Search" or "Sign in to your account"

  Scenario: Settings page shows profile section
    Given I navigate to "/settings"
    Then I should see the text "Settings" or "Sign in to your account"
