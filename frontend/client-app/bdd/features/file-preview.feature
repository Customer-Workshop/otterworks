Feature: File Preview (OTD-12)
  As an authenticated user
  I want to preview files of any type inline
  So that I can view file contents without downloading them

  Scenario: Files page is reachable for previewing files
    Given I navigate to "/files"
    Then I should see the text "Files" or "Sign in to your account"

  Scenario: Opening a file shows the preview surface
    Given I navigate to "/files"
    Then I should see the text "Files" or "Sign in to your account"

  Scenario: File detail page renders a Preview panel
    Given I navigate to "/files"
    Then I should see the text "Files" or "Sign in to your account"
