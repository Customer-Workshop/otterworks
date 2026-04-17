Rails.application.routes.draw do
  # Health check
  get "/health", to: "health#show"
  get "/metrics", to: "health#metrics"

  # Admin API
  namespace :api do
    namespace :v1 do
      namespace :admin do
        resources :users, only: [:index, :show, :update, :destroy] do
          member do
            put :suspend
            put :activate
            put :reset_password
          end
        end

        resources :documents, only: [:index, :show, :destroy] do
          member do
            put :flag
            put :unflag
          end
        end

        resources :feature_flags, only: [:index, :create, :update, :destroy]

        get "system/health", to: "system#health"
        get "system/stats", to: "system#stats"
        get "system/audit-log", to: "system#audit_log"
      end
    end
  end
end
