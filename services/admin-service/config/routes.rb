Rails.application.routes.draw do
  # Health check (excluded from JWT auth)
  get '/health', to: 'health#show'
  get '/metrics', to: 'health#metrics'

  # Admin API
  namespace :api do
    namespace :v1 do
      namespace :admin do
        # User Management
        resources :users, only: %i[index show update destroy] do
          member do
            put :suspend
            put :activate
          end
        end

        # System Health
        get 'health/services', to: 'health#services'

        # Feature Flags
        resources :features, only: %i[index show create update destroy]

        # System Configuration
        resources :config, only: %i[index show update]

        # Audit Log Viewer
        resources :audit_logs, only: %i[index show], path: 'audit-logs'

        # Storage Quotas
        get 'quotas/:user_id', to: 'quotas#show', as: :quota
        put 'quotas/:user_id', to: 'quotas#update'

        # System Metrics
        get 'metrics/summary', to: 'metrics#summary'

        # Announcements
        resources :announcements, only: %i[index show create update destroy]

        # Incidents (Automated Incident Response)
        resources :incidents, only: %i[index show create]

        # Bulk Operations
        post 'bulk/users', to: 'bulk#users'
      end
    end
  end
end
