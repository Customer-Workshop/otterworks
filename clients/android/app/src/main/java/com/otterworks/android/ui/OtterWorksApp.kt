package com.otterworks.android.ui

import androidx.compose.runtime.Composable
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.otterworks.android.OtterWorksApplication
import com.otterworks.android.ui.auth.AuthViewModel
import com.otterworks.android.ui.auth.LoginScreen
import com.otterworks.android.ui.auth.RegisterScreen
import com.otterworks.android.ui.documents.DocumentsScreen
import com.otterworks.android.ui.documents.DocumentsViewModel

object Routes {
    const val LOGIN = "login"
    const val REGISTER = "register"
    const val DOCUMENTS = "documents"
}

@Composable
fun OtterWorksApp(
    app: OtterWorksApplication,
    navController: NavHostController = rememberNavController(),
) {
    val start = if (app.repository.isLoggedIn()) Routes.DOCUMENTS else Routes.LOGIN

    NavHost(navController = navController, startDestination = start) {
        composable(Routes.LOGIN) {
            val vm: AuthViewModel = viewModel(factory = AppViewModelFactory.instance)
            LoginScreen(
                viewModel = vm,
                onLoggedIn = {
                    navController.navigate(Routes.DOCUMENTS) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
                onNavigateToRegister = { navController.navigate(Routes.REGISTER) },
            )
        }

        composable(Routes.REGISTER) {
            val vm: AuthViewModel = viewModel(factory = AppViewModelFactory.instance)
            RegisterScreen(
                viewModel = vm,
                onRegistered = {
                    navController.navigate(Routes.DOCUMENTS) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
                onNavigateToLogin = { navController.popBackStack() },
            )
        }

        composable(Routes.DOCUMENTS) {
            val vm: DocumentsViewModel = viewModel(factory = AppViewModelFactory.instance)
            DocumentsScreen(
                viewModel = vm,
                onLoggedOut = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                },
            )
        }
    }
}
