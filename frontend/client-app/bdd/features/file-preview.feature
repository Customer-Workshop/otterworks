Feature: File previews
  As an authenticated user
  I want to preview stored files inline
  So that I can inspect real files without downloading them

  Scenario: AC-01/BDD-01: opening a file from the file list shows an inline preview
    Given I am logged in as the seeded drive user
    When I open a seeded "png" file from the file list
    Then I should see an inline file preview

  Scenario: AC-05/BDD-05: an XLSX file renders as a table
    Given I am logged in as the seeded drive user
    When I open a seeded "xlsx" file from the file list
    Then I should see a spreadsheet table preview

  Scenario: AC-06/BDD-06: a CSV file renders as a table
    Given I am logged in as the seeded drive user
    When I open a seeded "csv" file from the file list
    Then I should see a spreadsheet table preview

  Scenario: AC-07/BDD-07: a DOCX file renders as a document
    Given I am logged in as the seeded drive user
    When I open a seeded "docx" file from the file list
    Then I should see a document preview

  Scenario: AC-11/BDD-11: an unsupported file renders the generic fallback
    Given I am logged in as the seeded drive user
    When I open a seeded "pptx" file from the file list
    Then I should see the generic file fallback

  Scenario: AC-18/BDD-18: an unauthenticated visitor is redirected to login
    Given I am logged out
    When I navigate to "/files/00000000-0000-0000-0000-000000000000"
    Then the URL should contain "/login"
