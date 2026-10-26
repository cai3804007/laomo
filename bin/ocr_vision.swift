// Vision OCR —— 输入若干图片，输出 JSON 行数组
// 关键点：usesLanguageCorrection = false
// 语言纠正会把价格数字"顺"成常见词（如 12.85 -> 12.8S / 一二八五），
// 在提取股价的场景下必须关掉。
import Foundation
import Vision
import AppKit

struct Line: Codable {
    let file: String
    let text: String
    let confidence: Float
    let x: Double, y: Double, w: Double, h: Double
}

let args = Array(CommandLine.arguments.dropFirst())
guard !args.isEmpty else {
    FileHandle.standardError.write("usage: ocr_vision <image...>\n".data(using: .utf8)!)
    exit(2)
}

var out: [Line] = []
for path in args {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        FileHandle.standardError.write("skip (unreadable): \(path)\n".data(using: .utf8)!)
        continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hans", "en-US"]
    req.usesLanguageCorrection = false
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    } catch {
        FileHandle.standardError.write("ocr failed: \(path): \(error)\n".data(using: .utf8)!)
        continue
    }
    let name = (path as NSString).lastPathComponent
    for obs in req.results ?? [] {
        guard let top = obs.topCandidates(1).first else { continue }
        let bb = obs.boundingBox
        out.append(Line(file: name, text: top.string, confidence: top.confidence,
                        x: bb.origin.x, y: bb.origin.y, w: bb.width, h: bb.height))
    }
}

let enc = JSONEncoder()
enc.outputFormatting = [.prettyPrinted, .withoutEscapingSlashes, .sortedKeys]
FileHandle.standardOutput.write(try! enc.encode(out))
FileHandle.standardOutput.write("\n".data(using: .utf8)!)
