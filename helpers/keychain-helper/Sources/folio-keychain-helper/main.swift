import Foundation
import LocalAuthentication
import Security

let service = "folio-cli"
let account = "master-key-v1"

struct Output: Codable {
    let ok: Bool
    let code: String?
    let message: String?
    let data_b64: String?
    let key_present: Bool?
    let biometric_capable: Bool?
}

func emit(_ out: Output, exitCode: Int32) -> Never {
    let encoder = JSONEncoder()
    if let data = try? encoder.encode(out), let str = String(data: data, encoding: .utf8) {
        print(str)
    } else {
        print("{\"ok\":false,\"code\":\"SERIALIZE\",\"message\":\"failed to serialize output\"}")
    }
    Foundation.exit(exitCode)
}

func queryBase() -> [String: Any] {
    [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecAttrAccount as String: account,
    ]
}

func status() {
    var q = queryBase()
    q[kSecReturnAttributes as String] = true
    q[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    let code = SecItemCopyMatching(q as CFDictionary, &result)
    if code == errSecSuccess {
        let canBio = LAContext().canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: nil)
        emit(Output(ok: true, code: nil, message: nil, data_b64: nil, key_present: true, biometric_capable: canBio), exitCode: 0)
    }
    if code == errSecItemNotFound {
        let canBio = LAContext().canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: nil)
        emit(Output(ok: true, code: nil, message: nil, data_b64: nil, key_present: false, biometric_capable: canBio), exitCode: 0)
    }
    emit(Output(ok: false, code: "SEC_STATUS", message: "SecItemCopyMatching failed: \(code)", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
}

func setKey(_ b64: String) {
    guard let data = Data(base64Encoded: b64) else {
        emit(Output(ok: false, code: "BAD_INPUT", message: "Invalid base64 key payload", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
    }

    let deleteCode = SecItemDelete(queryBase() as CFDictionary)
    if deleteCode != errSecSuccess && deleteCode != errSecItemNotFound {
        emit(Output(ok: false, code: "DELETE_FAILED", message: "SecItemDelete failed: \(deleteCode)", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
    }

    var add = queryBase()
    add[kSecValueData as String] = data
    let addCode = SecItemAdd(add as CFDictionary, nil)
    if addCode != errSecSuccess {
        emit(Output(ok: false, code: "SET_FAILED", message: "SecItemAdd failed: \(addCode)", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
    }
    emit(Output(ok: true, code: nil, message: nil, data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 0)
}

func authBiometric(prompt: String) {
    let context = LAContext()
    var err: NSError?
    let policy = LAPolicy.deviceOwnerAuthenticationWithBiometrics
    guard context.canEvaluatePolicy(policy, error: &err) else {
        let msg = err?.localizedDescription ?? "Biometric authentication not available"
        emit(Output(ok: false, code: "BIO_UNAVAILABLE", message: msg, data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
    }

    let sem = DispatchSemaphore(value: 0)
    var ok = false
    var message: String?
    context.evaluatePolicy(policy, localizedReason: prompt) { success, evalErr in
        ok = success
        if let evalErr {
            message = evalErr.localizedDescription
        }
        sem.signal()
    }
    _ = sem.wait(timeout: .now() + 120)
    if ok {
        emit(Output(ok: true, code: nil, message: nil, data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 0)
    }
    if let message, message.localizedCaseInsensitiveContains("canceled") || message.localizedCaseInsensitiveContains("cancelled") {
        emit(Output(ok: false, code: "AUTH_CANCELED", message: message, data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
    }
    emit(Output(ok: false, code: "BIO_FAILED", message: message ?? "Biometric authentication failed", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
}

func getKey(prompt: String) {
    var q = queryBase()
    q[kSecReturnData as String] = true
    q[kSecMatchLimit as String] = kSecMatchLimitOne
    q[kSecUseOperationPrompt as String] = prompt
    let context = LAContext()
    context.touchIDAuthenticationAllowableReuseDuration = 0
    q[kSecUseAuthenticationContext as String] = context

    var result: CFTypeRef?
    let code = SecItemCopyMatching(q as CFDictionary, &result)
    if code == errSecSuccess, let data = result as? Data {
        emit(Output(ok: true, code: nil, message: nil, data_b64: data.base64EncodedString(), key_present: nil, biometric_capable: nil), exitCode: 0)
    }
    if code == errSecItemNotFound {
        emit(Output(ok: false, code: "NOT_FOUND", message: "master key not found", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
    }
    emit(Output(ok: false, code: "GET_FAILED", message: "SecItemCopyMatching failed: \(code)", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
}

let args = CommandLine.arguments
guard args.count >= 2 else {
    emit(Output(ok: false, code: "USAGE", message: "usage: folio-keychain-helper <status|get|set> [args]", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
}

switch args[1] {
case "status":
    status()
case "set":
    guard args.count >= 3 else {
        emit(Output(ok: false, code: "USAGE", message: "usage: folio-keychain-helper set <base64-key>", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
    }
    setKey(args[2])
case "get":
    let prompt = args.count >= 3 ? args[2] : "Authenticate to access Folio key"
    getKey(prompt: prompt)
case "auth":
    let prompt = args.count >= 3 ? args[2] : "Authenticate to use Folio"
    authBiometric(prompt: prompt)
default:
    emit(Output(ok: false, code: "USAGE", message: "unknown command", data_b64: nil, key_present: nil, biometric_capable: nil), exitCode: 1)
}
