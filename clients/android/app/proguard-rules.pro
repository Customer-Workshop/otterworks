# Retrofit / Gson model classes are accessed reflectively; keep their fields.
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.otterworks.android.data.model.** { *; }
-keep class com.otterworks.android.data.remote.** { *; }
