plugins {
    kotlin("jvm") version "1.9.23"
    kotlin("plugin.serialization") version "1.9.23"
    id("io.ktor.plugin") version "2.3.9"
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

group = "com.otterworks"
version = "0.1.0"

application {
    mainClass.set("com.otterworks.notification.ApplicationKt")
}

repositories {
    mavenCentral()
}

dependencies {
    // Ktor Server
    implementation("io.ktor:ktor-server-core-jvm")
    implementation("io.ktor:ktor-server-netty-jvm")
    implementation("io.ktor:ktor-server-content-negotiation-jvm")
    implementation("io.ktor:ktor-server-status-pages-jvm")
    implementation("io.ktor:ktor-server-cors-jvm")
    implementation("io.ktor:ktor-serialization-kotlinx-json-jvm")
    implementation("io.ktor:ktor-server-metrics-micrometer-jvm")

    // Ktor Client (for calling other services)
    implementation("io.ktor:ktor-client-core-jvm")
    implementation("io.ktor:ktor-client-cio-jvm")
    implementation("io.ktor:ktor-client-content-negotiation-jvm")

    // AWS SDK
    implementation("aws.sdk.kotlin:sqs:1.0.70")
    implementation("aws.sdk.kotlin:sns:1.0.70")
    implementation("aws.sdk.kotlin:ses:1.0.70")
    implementation("aws.sdk.kotlin:dynamodb:1.0.70")

    // Serialization
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.0")

    // Logging
    implementation("ch.qos.logback:logback-classic:1.5.3")
    implementation("io.github.microutils:kotlin-logging-jvm:3.0.5")

    // Metrics
    implementation("io.micrometer:micrometer-registry-prometheus:1.12.4")

    // Testing
    testImplementation("io.ktor:ktor-server-tests-jvm")
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit:1.9.23")
    testImplementation("io.mockk:mockk:1.13.10")
}

kotlin {
    jvmToolchain(17)
}
