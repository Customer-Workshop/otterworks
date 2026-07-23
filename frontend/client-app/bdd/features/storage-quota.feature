Feature: Storage quota warning banner
  As a user
  I want a banner when I am near my storage quota
  So that I can free space before hitting the limit

  Scenario: Banner appears at or above 90% usage
    Given my storage usage is 90 percent of a "free" quota
    And I register and open the app
    Then I should see the storage warning banner
    And I should see the text "running low on storage"

  Scenario: Dismissing the banner hides it for the session
    Given my storage usage is 95 percent of a "free" quota
    And I register and open the app
    Then I should see the storage warning banner
    When I dismiss the storage warning banner
    Then the storage warning banner should not be visible

  Scenario: Banner action navigates to storage management
    Given my storage usage is 96 percent of a "free" quota
    And I register and open the app
    Then I should see the storage warning banner
    When I click the banner "Manage storage" action
    Then the URL should contain "/files"

  Scenario: No banner below 90 percent respecting tier quota_bytes
    Given my storage usage is 75 percent of a "pro" quota
    And I register and open the app
    Then the storage warning banner should not be visible
