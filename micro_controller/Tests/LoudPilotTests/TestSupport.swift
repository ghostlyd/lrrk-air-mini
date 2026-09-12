import Foundation

enum TestFailure: Error, CustomStringConvertible {
    case assertion(String)

    var description: String {
        switch self {
        case .assertion(let message): return message
        }
    }
}

func expect(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else { throw TestFailure.assertion(message) }
}

func expectThrows(_ operation: () throws -> Void) throws {
    do {
        try operation()
    } catch {
        return
    }
    throw TestFailure.assertion("expected operation to throw")
}
