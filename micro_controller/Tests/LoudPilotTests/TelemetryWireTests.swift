import LoudPilotCore

enum TelemetryWireTests {
    static func testLogTocInfoPacketUsesOnlyTheTelemetryLogPort() throws {
        let packet = try LiteWingTelemetryWire.logTOCInfoRequest()
        try expect(packet == [0x50, 0x03, 0x53], "TOC request should be a checksummed log packet")
        let decoded = try LiteWingTelemetryWire.decode(packet)
        try expect(decoded.header & 0xF0 == 0x50, "TOC request should use the log port")
    }

    static func testTelemetryCodecRejectsFlightControlPorts() throws {
        try expectThrows {
            _ = try LiteWingTelemetryWire.encode(
            header: 0x30,
            payload: [0, 0, 0, 0]
            )
        }
        try expectThrows {
            _ = try LiteWingTelemetryWire.encode(
            header: 0x70,
            payload: [0]
            )
        }
        try expectThrows {
            _ = try LiteWingTelemetryWire.encode(
            header: 0x80,
            payload: [0]
            )
        }
    }

    static func testLogTocItemIsDecodedWithoutInventingMissingValues() throws {
        let payload: [UInt8] = [
            0x02, 0x05, 0x00, 0x07,
            0x70, 0x6D, 0x00,
            0x76, 0x62, 0x61, 0x74, 0x00,
        ]
        let item = try LiteWingTelemetryWire.decodeTOCItem(payload)
        try expect(item.id == 5, "TOC item ID should be decoded")
        try expect(item.type == .float32, "TOC item type should be decoded")
        try expect(item.path == "pm.vbat", "TOC group and name should be decoded")
    }

    static func testLogSampleUpdatesBatteryAndIMUAndLeavesPositioningUnavailable() throws {
        let schema = LogBlockSchema(
            blockID: 1,
            variables: [
                LogVariable(id: 5, type: .float32, group: "pm", name: "vbat"),
                LogVariable(id: 9, type: .float32, group: "gyro", name: "x"),
                LogVariable(id: 10, type: .float32, group: "gyro", name: "y"),
                LogVariable(id: 11, type: .float32, group: "gyro", name: "z"),
            ]
        )
        var state = DroneTelemetryState()
        let bytes = [
            UInt8(1), 0x2A, 0x00, 0x00,
            0x66, 0x66, 0x76, 0x40, // 3.85 V
            0x00, 0x00, 0x20, 0x41, // 10
            0x00, 0x00, 0xA0, 0xC0, // -5
            0x00, 0x00, 0x00, 0x00, // 0
        ]
        try state.applyLogData(bytes, schema: schema, receivedAt: 123)

        try expect(abs((state.batteryVoltage ?? 0) - 3.85) < 0.0001, "battery voltage should decode")
        try expect(state.gyro == Optional(Vector3(x: 10, y: -5, z: 0)), "gyro should decode")
        try expect(state.positioning == nil, "unverified positioning must remain unavailable")
        try expect(state.telemetryAge(now: 123) == 0, "telemetry age should be computed from receive time")
    }

    static func testReadOnlyTelemetryRequiresBatteryGyroAndAccelerometer() throws {
        let gyroSchema = LogBlockSchema(
            blockID: 1,
            variables: [
                LogVariable(id: 1, type: .uint8, group: "pm", name: "vbat"),
                LogVariable(id: 2, type: .uint8, group: "gyro", name: "x"),
                LogVariable(id: 3, type: .uint8, group: "gyro", name: "y"),
                LogVariable(id: 4, type: .uint8, group: "gyro", name: "z"),
            ]
        )
        let accelerometerSchema = LogBlockSchema(
            blockID: 2,
            variables: [
                LogVariable(id: 5, type: .uint8, group: "acc", name: "x"),
                LogVariable(id: 6, type: .uint8, group: "acc", name: "y"),
                LogVariable(id: 7, type: .uint8, group: "acc", name: "z"),
            ]
        )
        var state = DroneTelemetryState()
        try state.applyLogData([1, 0, 0, 0, 4, 1, 2, 3], schema: gyroSchema, receivedAt: 1)
        try expect(!state.hasCompleteReadOnlyTelemetry, "partial battery and gyro data must not be considered complete telemetry")

        try state.applyLogData([2, 0, 0, 0, 5, 6, 7], schema: accelerometerSchema, receivedAt: 2)
        try expect(state.hasCompleteReadOnlyTelemetry, "battery, complete gyro, and complete accelerometer data should make telemetry complete")
    }

    static func testDiscoveryPlanUsesOnlyAdvertisedNonPositioningVariables() throws {
        let variables = [
            LogVariable(id: 1, type: .float32, group: "pm", name: "vbat"),
            LogVariable(id: 2, type: .float32, group: "gyro", name: "x"),
            LogVariable(id: 3, type: .float32, group: "gyro", name: "y"),
            LogVariable(id: 4, type: .float32, group: "gyro", name: "z"),
            LogVariable(id: 5, type: .float32, group: "acc", name: "x"),
            LogVariable(id: 6, type: .float32, group: "acc", name: "z"),
            LogVariable(id: 7, type: .float32, group: "position", name: "x"),
        ]

        let schemas = TelemetryDiscoveryPlan.schemas(from: variables)
        try expect(schemas.map(\.blockID) == [1, 2], "telemetry plan should use stable telemetry block IDs")
        try expect(schemas[0].variables.map(\.path) == ["pm.vbat", "gyro.x", "gyro.y", "gyro.z"], "primary schema should preserve advertised battery and gyro variables")
        try expect(schemas[1].variables.map(\.path) == ["acc.x", "acc.z"], "accelerometer schema should include only advertised axes")
        try expect(!schemas.flatMap(\.variables).contains { $0.group == "position" }, "positioning variables must not be inferred or subscribed to")
    }
}
