package com.cjxplorer.android.di

import com.cjxplorer.android.BuildConfig
import com.cjxplorer.android.data.websocket.CJXplorerWebSocketClient
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit
import javax.inject.Named
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
    @Named("wsBaseUrl")
    fun provideWsBaseUrl(): String = BuildConfig.WS_BASE_URL

    @Provides
    @Singleton
    fun provideWebSocketClient(
        okHttpClient: OkHttpClient,
        @Named("wsBaseUrl") wsBaseUrl: String
    ): CJXplorerWebSocketClient =
        CJXplorerWebSocketClient(okHttpClient, wsBaseUrl)
}
