package com.cjxplorer.android.di

import com.cjxplorer.android.data.repository.NavigationRepositoryImpl
import com.cjxplorer.android.domain.repository.NavigationRepository
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class CJXplorerAppModule {

    @Binds
    @Singleton
    abstract fun bindNavigationRepository(
        impl: NavigationRepositoryImpl
    ): NavigationRepository
}
