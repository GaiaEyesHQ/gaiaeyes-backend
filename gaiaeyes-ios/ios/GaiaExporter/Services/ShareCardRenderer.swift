#if canImport(UIKit)
import SwiftUI
import UIKit

@MainActor
enum ShareCardRenderer {
    static func render(card: ShareCardModel, backgroundImage: UIImage?) -> UIImage? {
        let size = card.format.canvasSize
        let content = ShareCardView(model: card, backgroundImage: backgroundImage)
            .frame(width: size.width, height: size.height)

        let renderer = ImageRenderer(content: content)
        renderer.scale = UIScreen.main.scale
        renderer.proposedSize = ProposedViewSize(width: size.width, height: size.height)
        return renderer.uiImage
    }
}
#endif
