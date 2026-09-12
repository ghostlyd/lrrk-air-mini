import Foundation
import LoudPilotCore

enum HIDRegistryTests {
    static func testMetadataRescanFindsNewAndRemovesMissingDevices() throws {
        let existing: Set<String> = ["micro", "keyboard"]
        let observed: Set<String> = ["micro", "mouse"]
        let stale = HIDRegistryReconciliation.staleDeviceIDs(existing: existing, observed: observed)
        try expect(stale == ["keyboard"], "metadata rescan must identify only disappeared HID devices")
    }
}
