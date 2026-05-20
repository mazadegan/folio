// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "folio-keychain-helper",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(name: "folio-keychain-helper", targets: ["folio-keychain-helper"]),
    ],
    targets: [
        .executableTarget(
            name: "folio-keychain-helper",
            path: "Sources/folio-keychain-helper"
        ),
    ]
)

