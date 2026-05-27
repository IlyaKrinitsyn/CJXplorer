package com.cjxplorer.android.di

import com.cjxplorer.android.data.settings.CJXplorerSettingsRepository
import com.cjxplorer.android.data.websocket.CJXplorerDeviceClient
import com.cjxplorer.android.data.websocket.CJXplorerWebSocketClient
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object CJXplorerNetworkModule {

    @Provides
    @Singleton
    fun provideOkHttpClient(): OkHttpClient =
        OkHttpClient.Builder()
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()

    @Provides
    @Singleton
    fun provideWebSocketClient(
        okHttpClient: OkHttpClient,
        settingsRepository: CJXplorerSettingsRepository
    ): CJXplorerWebSocketClient =
        CJXplorerWebSocketClient(okHttpClient, settingsRepository)

    @Provides
    @Singleton
    fun provideDeviceClient(
        okHttpClient: OkHttpClient,
        settingsRepository: CJXplorerSettingsRepository
    ): CJXplorerDeviceClient =
        CJXplorerDeviceClient(okHttpClient, settingsRepository)
}
