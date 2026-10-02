// Frame and body-pose helper for tools/physique.py. Runs on the Mac only.
//
//   pxtool info <video>                          -> {"duration": s, "date": "YYYY-MM-DD"}
//   pxtool frames <video> <every s> <dir> <h> [from s] [to s]  -> small frames for a contact sheet, prints their times
//   pxtool frame <video> <t> <out.jpg>           -> one full-size frame
//   pxtool pose <img>...                         -> one JSON line of joints per image, top-left origin, 0 to 1
//
// Frames come through AVFoundation so iPhone HDR video is tone-mapped to SDR and rotation is applied.

import Foundation
import AVFoundation
import Vision
import ImageIO
import UniformTypeIdentifiers

func fail(_ s: String) -> Never { FileHandle.standardError.write((s + "\n").data(using: .utf8)!); exit(1) }

func writeJPEG(_ img: CGImage, _ path: String, quality: Double = 0.92) {
    guard let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: path) as CFURL, UTType.jpeg.identifier as CFString, 1, nil) else { fail("cannot write \(path)") }
    CGImageDestinationAddImage(dest, img, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
    if !CGImageDestinationFinalize(dest) { fail("cannot write \(path)") }
}

func generator(_ asset: AVURLAsset, maxHeight: CGFloat? = nil) -> AVAssetImageGenerator {
    let g = AVAssetImageGenerator(asset: asset)
    g.appliesPreferredTrackTransform = true
    g.requestedTimeToleranceBefore = .zero
    g.requestedTimeToleranceAfter = .zero
    g.dynamicRangePolicy = .forceSDR
    if let h = maxHeight { g.maximumSize = CGSize(width: h * 4, height: h) }
    return g
}

func json(_ o: Any) -> String {
    String(data: try! JSONSerialization.data(withJSONObject: o, options: [.sortedKeys]), encoding: .utf8)!
}

let args = Array(CommandLine.arguments.dropFirst())
guard let cmd = args.first else { fail("usage: pxtool info|frames|frame|pose ...") }

switch cmd {
case "info":
    let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
    let dur = try await asset.load(.duration).seconds
    var out: [String: Any] = ["duration": dur]
    if let item = try await asset.load(.creationDate), let d = try await item.load(.dateValue) {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.locale = Locale(identifier: "en_US_POSIX")
        out["date"] = f.string(from: d)
    }
    print(json(out))

case "frames":
    let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
    let every = Double(args[2])!, dir = args[3], h = CGFloat(Double(args[4])!)
    let dur = try await asset.load(.duration).seconds
    let g = generator(asset, maxHeight: h)
    var times: [Double] = []
    var t = args.count > 5 ? Double(args[5])! : 0.0
    let end = args.count > 6 ? min(Double(args[6])!, dur) : dur
    while t < end - 0.05 {
        let img = try await g.image(at: CMTime(seconds: t, preferredTimescale: 600)).image
        writeJPEG(img, String(format: "%@/f%04d.jpg", dir, times.count), quality: 0.8)
        times.append((t * 100).rounded() / 100)
        t += every
    }
    print(json(["duration": dur, "times": times]))

case "frame":
    let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
    let img = try await generator(asset).image(at: CMTime(seconds: Double(args[2])!, preferredTimescale: 600)).image
    writeJPEG(img, args[3])

case "pose":
    let joints: [(String, VNHumanBodyPoseObservation.JointName)] = [
        ("nose", .nose), ("neck", .neck), ("ls", .leftShoulder), ("rs", .rightShoulder),
        ("le", .leftElbow), ("re", .rightElbow), ("lw", .leftWrist), ("rw", .rightWrist),
        ("lh", .leftHip), ("rh", .rightHip), ("root", .root),
        ("lk", .leftKnee), ("rk", .rightKnee), ("la", .leftAnkle), ("ra", .rightAnkle)
    ]
    for path in args.dropFirst() {
        var out: [String: Any] = ["path": path]
        let req = VNDetectHumanBodyPoseRequest()
        do {
            try VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:]).perform([req])
            // The biggest person in the frame is the subject; a mirror can show a second, smaller one.
            let best = (req.results ?? []).max { a, b in
                func spread(_ o: VNHumanBodyPoseObservation) -> CGFloat {
                    let ps = ((try? o.recognizedPoints(.all)) ?? [:]).values.filter { $0.confidence > 0.3 }.map(\.location)
                    guard let x0 = ps.map(\.x).min(), let x1 = ps.map(\.x).max(), let y0 = ps.map(\.y).min(), let y1 = ps.map(\.y).max() else { return 0 }
                    return (x1 - x0) * (y1 - y0)
                }
                return spread(a) < spread(b)
            }
            if let o = best, let pts = try? o.recognizedPoints(.all) {
                for (k, j) in joints {
                    if let p = pts[j], p.confidence > 0.3 {
                        out[k] = [Double(p.location.x), Double(1 - p.location.y), Double(p.confidence)]
                    }
                }
            }
        } catch {
            out["error"] = "\(error)"
        }
        print(json(out))
    }

default:
    fail("unknown command \(cmd)")
}
