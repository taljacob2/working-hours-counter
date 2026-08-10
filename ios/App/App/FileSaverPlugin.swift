import Foundation
import Capacitor

// iOS counterpart to android/app/src/main/java/com/taljacob/workinghours/FileSaverPlugin.java —
// same saveFile({content, filename, mimeType, isBase64}) contract, so src/lib/exportUtils.js
// needs no platform branching. Uses UIDocumentPickerViewController so the user picks a save
// location in the Files app, matching Android's ACTION_CREATE_DOCUMENT picker.
@objc(FileSaverPlugin)
public class FileSaverPlugin: CAPPlugin, CAPBridgedPlugin, UIDocumentPickerDelegate {
    public let identifier = "FileSaverPlugin"
    public let jsName = "FileSaver"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "saveFile", returnType: CAPPluginReturnPromise)
    ]

    private var pendingCall: CAPPluginCall?
    private var tempFileURL: URL?

    @objc func saveFile(_ call: CAPPluginCall) {
        let filename = call.getString("filename") ?? "export.csv"
        let content = call.getString("content") ?? ""
        let isBase64 = call.getBool("isBase64") ?? false

        let data: Data?
        if isBase64 {
            data = Data(base64Encoded: content)
        } else {
            data = content.data(using: .utf8)
        }
        guard let fileData = data else {
            call.reject("Failed to decode content")
            return
        }

        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent(filename)
        do {
            try fileData.write(to: tempURL, options: .atomic)
        } catch {
            call.reject("Write failed: \(error.localizedDescription)")
            return
        }

        pendingCall = call
        tempFileURL = tempURL

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            let picker = UIDocumentPickerViewController(forExporting: [tempURL], asCopy: true)
            picker.delegate = self
            self.bridge?.viewController?.present(picker, animated: true)
        }
    }

    public func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        cleanupTempFile()
        pendingCall?.resolve()
        pendingCall = nil
    }

    public func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        cleanupTempFile()
        pendingCall?.reject("cancelled")
        pendingCall = nil
    }

    private func cleanupTempFile() {
        if let url = tempFileURL {
            try? FileManager.default.removeItem(at: url)
        }
        tempFileURL = nil
    }
}
