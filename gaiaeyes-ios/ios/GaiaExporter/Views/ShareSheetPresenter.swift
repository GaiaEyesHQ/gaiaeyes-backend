#if canImport(UIKit)
import SwiftUI
import UIKit

#if canImport(LinkPresentation)
import LinkPresentation
#endif

struct ShareSheetPresenter: UIViewControllerRepresentable {
    let image: UIImage
    let text: String
    let title: String
    let subtitle: String?
    let onComplete: (Bool) -> Void

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let itemSource = ShareImageActivitySource(
            image: image,
            title: title,
            subtitle: subtitle
        )
        let controller = UIActivityViewController(
            activityItems: [itemSource, text],
            applicationActivities: nil
        )
        controller.completionWithItemsHandler = { _, completed, _, _ in
            onComplete(completed)
        }
        return controller
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

private final class ShareImageActivitySource: NSObject, UIActivityItemSource {
    let image: UIImage
    let title: String
    let subtitle: String?

    init(image: UIImage, title: String, subtitle: String?) {
        self.image = image
        self.title = title
        self.subtitle = subtitle
    }

    func activityViewControllerPlaceholderItem(_ activityViewController: UIActivityViewController) -> Any {
        image
    }

    func activityViewController(
        _ activityViewController: UIActivityViewController,
        itemForActivityType activityType: UIActivity.ActivityType?
    ) -> Any? {
        image
    }

    #if canImport(LinkPresentation)
    func activityViewControllerLinkMetadata(_ activityViewController: UIActivityViewController) -> LPLinkMetadata? {
        let metadata = LPLinkMetadata()
        metadata.title = [title, subtitle].compactMap { value in
            guard let value, !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                return nil
            }
            return value
        }.joined(separator: " • ")
        metadata.originalURL = URL(string: "https://gaiaeyes.app")
        metadata.url = metadata.originalURL
        metadata.iconProvider = NSItemProvider(object: image)
        metadata.imageProvider = NSItemProvider(object: image)
        return metadata
    }
    #endif
}
#endif
