# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class kotlinx.serialization.json.** { kotlinx.serialization.KSerializer serializer(...); }
-keep,includedescriptorclasses class com.cjxplorer.android.**$$serializer { *; }
-keepclassmembers class com.cjxplorer.android.** { *** Companion; }
-keepclasseswithmembers class com.cjxplorer.android.** { kotlinx.serialization.KSerializer serializer(...); }
