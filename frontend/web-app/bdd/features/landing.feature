Feature: Landing Page
  As a visitor
  I want to see the OtterWorks landing page
  So that I can learn about the product and sign up

  Scenario: Visitor sees the hero section
    Given I am on the landing page
    Then I should see the heading "OtterWorks"
    And I should see the text "Collaborative document and file management"

  Scenario: Visitor sees navigation CTAs
    Given I am on the landing page
    Then I should see a link "Sign In"
    And I should see a link "Create Account"

  Scenario: Visitor sees all feature cards
    Given I am on the landing page
    Then I should see the text "File Management"
    And I should see the text "Document Editing"
    And I should see the text "Real-time Collaboration"
    And I should see the text "Powerful Search"
    And I should see the text "Secure Sharing"
    And I should see the text "Instant Notifications"

  Scenario: Sign In link navigates to login
    Given I am on the landing page
    When I click the link "Sign In"
    Then the URL should contain "/login"

  Scenario: Create Account link navigates to register
    Given I am on the landing page
    When I click the link "Create Account"
    Then the URL should contain "/register"

  Scenario: Footer is visible
    Given I am on the landing page
    Then I should see the text "Collaborative document & file management platform"
